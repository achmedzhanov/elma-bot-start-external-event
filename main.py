import io
from datetime import datetime, timedelta
import streamlit as st
import requests
import zipfile
import json
import pandas as pd
from time import sleep


st.set_page_config(page_title="⚡Запуск триггера бота")
st.title("⚡Запуск триггера бота")


st.sidebar.header("Параметры подключения")
base_url = st.sidebar.text_input(
    "Базовый URL:", placeholder="Адрес стенда", value="https://client.elma-bot.ai"
)
bot_id = st.sidebar.text_input(
    "Идентификатор бота:", placeholder="Открыть конструктор ботов > Настройки > API"
)
xtoken = st.sidebar.text_input(
    "X-Token", placeholder="Открыть конструктор ботов > Настройки > API"
)

events_list_tab, notify_tab = st.tabs(["Список событий", "Запустить notify"])

with events_list_tab:

    get_event_descriptions = st.button("Получить список событий")

    if get_event_descriptions:
        if not base_url or not bot_id or not xtoken:
            st.warning("Необходимо заполнить все поля")
            st.stop()
        events_list_url = base_url + "/api/v1/runtime/simple/external/events/" + bot_id
        response = requests.get(url=events_list_url, headers={"X-Token": xtoken})
        if response.status_code == 401:
            st.warning("Ошибка авторизации")
        elif response.status_code != 200:
            st.warning("Не удалось загрузить информацию о событиях")
            st.write(response)
        else:
            events = response.json()
            st.text("События")
            for e in events:
                externalEventId = e["externalEventId"]
                parameters = e["parameters"]
                st.markdown(f"**externalEventId**: {externalEventId}")
                st.markdown(f"**parameters**: {parameters}")
                st.divider()
        # st.write(response.json())


with notify_tab:
    st.markdown("Запустить событие notify с параметром notify_text")
    notify_text = st.text_area("Текст уведомления")

    one_conversation = "Одна беседа (по id)"
    by_date = "Беседы за указанный период"
    target_type = st.radio(
        "Аудитория",
        [one_conversation, "Все беседы", by_date],
        captions=[
            "удобно использовать для пробного запуска.",
            "Если нужно разослать всем пользователям.",
            "Если нужно разослать тем, кто пользуется ботом в указанный период (например неделя).",
        ],
    )

    if target_type == one_conversation:
        conversation_id = st.text_input('id беседы')
        if run_submited := st.button('Запустить'):
            if not conversation_id:
                st.warning('Необходим указать идентификатор беседы')
                st.stop()
            if not notify_text:
                st.warning('Необходим указать текст уведомления')
                st.stop()   

            st.info('Запуск...')
            start_event__url = base_url + '/api/v1/runtime/simple/external/events'
            data = {
                'conversationId': conversation_id,
                'externalEventId': 'notify',
                'externalEventPayload': {
                    'notify_text': notify_text
                }
            }
            r = requests.post(start_event__url, json=data, headers={"X-Token": xtoken, 'Content-Type': 'application/json'})
            if r.status_code == 200:
                st.success('Событие успешно запущено')
            else:
                st.warning('Что то пошло не так')
                st.write(r)
    elif target_type == by_date:
        today = datetime.now()
        week_ago = today  - timedelta(7)
        (date_range_from, date_range_to) = st.date_input(
            "Выберите дни, по которым будут выбраны активные беседы",
            (week_ago, today),
            week_ago,
            today,
            format="DD.MM.YYYY",
        )

        if run_submited := st.button('Найти беседы'):

            export_url = base_url + '/api/v1/dialogs/export'
            export_payload = {
                'agentStageId': bot_id,
                'status': 'Active',
                'latestMessageFromDate': date_range_from.strftime('%Y-%m-%d'),
                'latestMessageToDate': date_range_to.strftime('%Y-%m-%d')
            }
            load_placeholder = st.empty()
            load_placeholder.text('Экспортируем список бесед')
            load_placeholder.write(export_payload)
            r = requests.post(export_url, json=export_payload, headers={"X-Token": xtoken, 'Content-Type': 'application/json'})
            
            if r.status_code != 200:
                st.warning('Не удалось выполнить экспорт')
                st.write(r)
                st.stop()
            request_id = r.json()['requestId']

            check_status_url = base_url + '/api/v1/dialogs/export/status/' + request_id
            while True:
                r = requests.get(check_status_url, headers={"X-Token": xtoken} ).json()
                status = r['status']
                if status == 'Success':
                    file_url = r['fileUrl']
                    break
                elif status == 'Error':
                    st.warning('Ошибка экспорта')
                    st.write(r.json())
            load_placeholder.write(f'Скачивается файл с беседами {file_url}')
            response = requests.get(file_url)
            conversations = []
            with zipfile.ZipFile(io.BytesIO(response.content)) as thezip:
                for zipinfo in thezip.infolist():
                    with thezip.open(zipinfo, mode='r') as file:
                        data = json.loads(file.read())
                        id = data['id']
                        user_name = [m for m in data['members'] if m['role'] == 'User'][0]['name']
                        conversations.append((id, user_name))
            
            st.session_state.conversations = conversations
            
        if st.session_state.conversations:
            st.header('Беседы')
            st.write(pd.DataFrame(st.session_state.conversations, columns=['id', 'Имя клиента']))
            st.write(f'Найдено {len(st.session_state.conversations)} бесед')

            if continue_submited := st.button('Запустить рассылку'):
                # st.write('Запускается рассылка')
                progress = st.progress(0, 'Запуск событий для найденных бесед')
                runs_expander = st.expander('Запуски')
                for i, (conversation_id,_) in enumerate(st.session_state.conversations):
                    runs_expander.write(conversation_id)
                    start_event__url = base_url + '/api/v1/runtime/simple/external/events'
                    data = {
                        'conversationId': conversation_id,
                        'externalEventId': 'notify',
                        'externalEventPayload': {
                            'notify_text': notify_text
                        }
                    }
                    r = requests.post(start_event__url, json=data, headers={"X-Token": xtoken, 'Content-Type': 'application/json'})
                    if r.status_code == 200:
                        runs_expander.success('Событие успешно запущено')
                    else:
                        runs_expander.warning('Что то пошло не так')
                        runs_expander.write(r)
                    sleep(1)
                    progress.progress((i + 1) / len(st.session_state.conversations))

    else:
        st.warning('Этот тип аудитории пока не поддерживается')
