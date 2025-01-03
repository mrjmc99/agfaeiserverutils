# agfaEiServerUtils\common\api.py
import logging
import requests


# function to get auth token
def get_token(EI_FQDN,EI_USER,EI_PASSWORD):
    global TOKEN
    logging.info(f"Getting a token for user {EI_USER}")
    auth_url = f"https://{EI_FQDN}/authentication/token"
    params = {"user": EI_USER, "password": EI_PASSWORD}

    try:
        response = requests.get(auth_url, params=params, verify=False)
        response.raise_for_status()
        TOKEN = response.text.split('CDATA[')[1].split(']]')[0]
        logging.info("Token acquired successfully.")
        return TOKEN
    except requests.HTTPError as e:
        if e.response.status_code == 403:
            logging.error("Token acquisition failed: HTTP 403 Forbidden. Check credentials or permissions.")
        else:
            logging.error(f"Failed to acquire token. Error: {str(e)}")
        return False
    except requests.RequestException as e:
        logging.error(f"Failed to acquire token. Error: {str(e)}")
        return False


# function to release token
def release_token(EI_FQDN):
    logging.info(f"Releasing token")
    auth_url = f"https://{EI_FQDN}/authentication/logout"
    headers = {"Authorization": f"Bearer {TOKEN}"}

    try:
        response = requests.get(auth_url, headers=headers, verify=False)
        response.raise_for_status()
        logging.info("Token released successfully.")
        return True  # Indicate successful token release
    except requests.RequestException as e:
        logging.error(f"Failed to release token. Error: {str(e)}")
        return False  # Indicate failed token release


# Function to look up available CS Nodes
def lookup_available_nodes(EI_FQDN,EI_USER,EI_PASSWORD):
    logging.info("Calling EI API")
    token_acquired = get_token(EI_FQDN,EI_USER,EI_PASSWORD)

    if not token_acquired:
        logging.error("Unable to acquire token. Skipping API call.")
        return "Unable to look up Cluster"

    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
    cluster_url = f"https://{EI_FQDN}/ris/web/v2/queues/availableNodes"

    try:
        response = requests.get(cluster_url, headers=headers, verify=True)
        response.raise_for_status()
        logging.info("API call successful.")
        logging.info(response.text)
        return response.text
    except requests.RequestException as e:
        logging.error(f"API call failed. Error: {str(e)}")
        return "Unable to look up Cluster"
    finally:
        release_token(EI_FQDN)