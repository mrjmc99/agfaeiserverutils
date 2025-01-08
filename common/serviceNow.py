# agfaEiServerUtils\common\serviceNow.py

import os
import requests


# Function to create service now tickets
def create_service_now_incident(summary, description, affected_user_id, configuration_item, external_unique_id, urgency,
                                impact,service_now_instance,service_now_table,service_now_api_user, service_now_api_password, assignment_group):
    service_now_api_url = f"https://{service_now_instance}/api/now/table/{service_now_table}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "u_short_description": summary,
        "u_description": description,
        "u_affected_user_id": affected_user_id,
        "u_configuration_item": configuration_item,
        "u_external_unique_id": external_unique_id,
        "u_urgency": urgency,
        "u_impact": impact,
        "u_type": 'incident',
        "u_assignment_group": assignment_group,
    }

    try:
        print("Ticket Creation Payload:", payload)  # Print payload for debugging
        response = requests.post(
            service_now_api_url,
            headers=headers,
            auth=(service_now_api_user, service_now_api_password),
            json=payload,
        )

        print("Ticket Creation Response Status Code:", response.status_code)  # Print status code for debugging
        print("Ticket Creation Response Content:", response.text)  # Print response content for debugging

        if response.status_code == 201:
            incident_number = response.json().get("result", {}).get("u_task_string")
            sys_id = response.json().get('result', {}).get('u_task', {}).get('value')
            print(f"ServiceNow incident created successfully: {incident_number} {sys_id}")
            return incident_number, sys_id
        else:
            print(f"Failed to create ServiceNow incident. Response: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while creating ServiceNow incident: {e}")

    return None, None


def attach_file_to_ticket(sys_id, file_path,service_now_instance,service_now_attachment_table,service_now_api_user, service_now_api_password):
    attachment_api_url = f"https://{service_now_instance}/api/now/attachment/upload"

    headers = {
        "Accept": "application/json",
    }

    data = {
        "Content-Type": "application/octet-stream",
        "table_name": service_now_attachment_table,
        "table_sys_id": sys_id,
        "filename": os.path.basename(file_path),
    }

    files = {
        'file': (os.path.basename(file_path), open(file_path, 'rb')),
    }

    try:
        print("Sending attachment request...")
        print("Headers:", headers)
        print("Data:", data)
        print("Files:", files)
        attachment_response = requests.post(
            attachment_api_url,
            headers=headers,
            auth=(service_now_api_user, service_now_api_password),
            data=data,
            files=files,
        )

        print("Attachment response status code:", attachment_response.status_code)
        print("Attachment response text:", attachment_response.text)

        if attachment_response.status_code == 201:
            print("File attached to ServiceNow Ticket successfully")
        else:
            print(f"Failed to attach file to ServiceNow Ticket. Response: {attachment_response.text}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while attaching the file to ServiceNow Ticket: {e}")


def create_service_now_request(summary, description, affected_user_id,service_now_instance,service_now_table,service_now_api_user, service_now_api_password, assignment_group,request_catalog_item,request_u_description ):
    service_now_api_url = f"https://{service_now_instance}/api/now/table/{service_now_table}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "u_type": 'request',
        "u_requested_by_user_id": affected_user_id,
        "u_affected_user_id": affected_user_id,
        #"u_phone": '123-456-7890',
        #"u_email": 'pacstest@pacs.com',
        "u_catalog_item": request_catalog_item,
        "u_description": request_u_description,
        "u_variables": f"assignment_group::{assignment_group}::priority::3::assignee"
                       f"::::short_description::{summary}"
                       f"::description::{description}"
                       f"::requester::::affected_user::::email::"
                       f"::phone::::requester_location::::affected_user_location::::"
    }

    try:
        print("Ticket Creation Payload:", payload)  # Print payload for debugging
        response = requests.post(
            service_now_api_url,
            headers=headers,
            auth=(service_now_api_user, service_now_api_password),
            json=payload,
        )

        print("Ticket Creation Response Status Code:", response.status_code)  # Print status code for debugging
        print("Ticket Creation Response Content:", response.text)  # Print response content for debugging

        if response.status_code == 201:
            ticket_number = response.json().get("result", {}).get("u_task_string")
            sys_id = response.json().get('result', {}).get('u_task', {}).get('value')
            print(f"ServiceNow Request created successfully: {ticket_number} {sys_id}")
            return ticket_number, sys_id
        else:
            print(f"Failed to create ServiceNow incident. Response: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while creating ServiceNow incident: {e}")

    return None, None