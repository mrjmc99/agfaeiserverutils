# Agfa Enterprise Imaging Scripts

This repository contains **three** primary Python scripts, each designed to manage or monitor different aspects of an Agfa Enterprise Imaging environment. All three scripts rely on a **common code base** found in the `common` folder for shared functionality such as EI API calls, email sending, and ServiceNow integrations.

---

## Table of Contents

1. [Overview](#overview)  
2. [Common Prerequisites](#common-prerequisites)  
3. [Script 1: Error Report Processing Script](#error-report-processing-script)  
4. [Script 2: JBoss Check Script](#jboss-check-script)  
5. [Script 3: Xero Ticket Management Script](#xero-ticket-management-script)  
6. [Support and Issues](#support-and-issues)

---

## Overview

1. **Client Error Reports**  
   - Monitors and processes Enterprise Imaging error reports (zip files), creates ServiceNow incidents, and sends email notifications.  
   - Typically scheduled on each Core Server to handle local error reports.

2. **JBoss Check Script**  
   - Monitors JBoss EAP instances in a cluster, scans log files for crash dumps or “started/stopped” events, and sends alerts (email, ServiceNow tickets) if issues are found.

3. **Xero Ticket Management Script**  
   - Automates creation and verification of Xero tickets, checks server status, restarts or disables servers, and integrates with ServiceNow for incident creation.

All scripts share some **common** functionalities:
- Reading from an `.env` file for environment-specific settings.
- Sending email notifications.
- Creating incidents or requests in ServiceNow.
- Logging activities to a log file for troubleshooting.

---

## Common Prerequisites

1. **Python 3.11+ installed**  
   Make sure Python is installed on each machine where you plan to run these scripts.

2. **Install Python Dependencies**  
   Each script (and the common code) has a `requirements.txt` or combined dependencies. Typically:
   ```bash
   pip install -r requirements.txt
    ```
**Agfa Oracle Linux 8 VM install**

When using the Stock Agfa OL8 OVA, you will need to remove python 3.6 and upgrade to 3.11 or greater, for example:

    dnf remove python3 -y
    dnf install python3.12 python3.12-pip -y


Make sure to do this within a virtual environment (venv) or system-wide, depending on your environment.

Environment Files
Each script expects its own .env file (e.g., error-report.env, jboss-check.env, xeroticket.env), but they share a similar structure:

Email server settings
ServiceNow credentials
Paths or domain information
Any script-specific variables (e.g., JBoss log directory, Xero server list, etc.)
SMTP Access (Optional)
If you plan to send out email alerts, you’ll need access to an SMTP server.

ServiceNow Access (Optional)
If you plan to create incidents or requests in ServiceNow, you’ll need valid API credentials and knowledge of the correct tables/fields.

SSH Keys (For Xero Ticket Management)
If the script restarts or disables remote Xero servers via SSH, ensure that the necessary SSH keys and sudo permissions are in place.


# Error Report Processing Script

This script is designed to process error reports generated by a system and take appropriate actions, including creating incidents in ServiceNow and sending email notifications.

This script is intended to be ran on each Core Server as error reports can be saved on any Core Server behind the EI FQDN (VIP) as a scheduled task. This can be configured to run at the interval of your choice, for example every 5 minutes.

You will need to work with your servicenow development team to get the correct tables, guids, and accounts for ticket creation.

If you wish to use the email functionality, you will need access to an SMTP server.

## Prerequisites

Before running the script, ensure the following:

- Email SMTP server and credentials if required.
- ServiceNow api user, table and guid specifics for your instance

## Configuration

The script uses a Environment file named `error-report.env` to store various parameters. Ensure that this file is present in the same directory as the script. Example Environment parameters include:

- Agfa Variables
- Email Variables
- ServiceNow Variables
- Excluded Items Variables

## Usage

Run the script using the following command:

```bash
python error_report_script.py
```

To run on Linux create a bash script, eg:
```bash
#!/bin/bash
 
# Set the environment variable for COMPUTERNAME
export COMPUTERNAME=$(hostname -s | tr '[:lower:]' '[:upper:]')
 
# Run the Python script
python3 /opt/scripts/agfaeiserverutils/clientErrorReports/error-report.py
```


The script will process error reports, create incidents in ServiceNow, and send email notifications based on the Environment.

## Script Logic

1. **Configuration Loading**: Load Environment parameters from the `error-report.env` file.

2. **Business Hours Check**: Determine the urgency and impact based on business hours.

3. **Excluded Items Check**: Exclude certain items from processing based on predefined lists.

4. **Email Sending**: Send email notifications with error report details.

5. **ServiceNow Ticket Creation**: Create Tickets in ServiceNow with relevant details.

6. **Attachment Handling**: Attach the error report file to the created ServiceNow Ticket.

7. **Processing Loop**: The script processes each error report found in the source folder.

## Error Report Format

The script expects error reports to be in a specific format, including a zip file containing logs and a `comment.txt` file.

## Excluded Items

You can specify computer names and user codes to be excluded from ServiceNow processing in the `excluded_computer_names_path` and `excluded_user_codes_path` files, respectively.



# JBoss Check Script

## Overview

The **JBoss Check Script** is a Python script designed to monitor and report the health status of JBoss EAP (Enterprise Application Platform) instances in a cluster. The script checks the status of JBoss EAP nodes, processes log files, and sends email notifications based on certain events.

## Features

- **Cluster Node Health Check**: The script performs health checks on JBoss EAP cluster nodes to ensure their availability.

- **Log File Monitoring**: Monitors JBoss EAP log files for specific events, capturing the newest event and sending email notifications.

- **Jboss Crash Monitoring**: Monitors JBoss EAP folder for Crash Dump Files, if found, a ServiceNow ticket is generated, Email Alert is sent, and Crashdump file moved to a secondary location.

- **Email Notifications**: Sends email notifications with relevant information about the latest JBoss EAP events.

## Prerequisites

A user that has minimal permissions in EI, for example I created an agility user named "Monitor" and assigned it the permission set of monitoring, this is required to lookup the cluster status.
  

## Configuration

The script uses a Environment file named **jboss-check.env** for various settings. Ensure that the Environment file is correctly set up before running the script.

### Environment Parameters

- **Agfa Section:**
  - `EI_FQDN`: FQDN of the Enterprise Imaging (EI) API.
  - `EI_USER`: Username for accessing the EI API.
  - `EI_PASSWORD`: Password for accessing the EI API.
  - `log_dir`: Directory containing JBoss EAP log files.
  - `last_processed_event_file`: Path to the file storing the information about the last processed event.
  - `crashdump_logs_folder`: Path to store Jboss Crash dumps
  - `EI_jboss_path` : Path to EI Jboss

- **Email Section:**
  - `smtp_server`: SMTP server for sending email notifications.
  - `smtp_port`: SMTP server port.
  - `smtp_username`: Username for SMTP server authentication.
  - `smtp_password`: Password for SMTP server authentication.
  - `smtp_from_domain`: Domain for the 'From' address in email notifications.
  - `smtp_recipients`: Comma-separated list of email addresses to receive notifications.

- **ServiceNow Section:**
  - `api_user`: ServiceNow API Username.
  - `api_password`: ServiceNow API Password.
  - `instance`: ServiceNow Instance URL.
  - `table`: ServiceNow Table.
  - `ticket_type`: ServiceNow Ticket Type.
  - `configuration_item`: ServiceNow Configuration Item (GUID).
  - `assignment_group`: ServiceNow Assignment Group (GUID).
  - `assignee`: ServiceNow assignee (GUID).
  - `business_hours_start_time`: Business Hours Start Time.
  - `business_hours_end_time`: Business Hours End Time.
  - `after_hours_urgency`: ServiceNow After Hours Urgency.
  - `after_hours_impact`: ServiceNow After Hours Impact.
  - `business_hours_urgency`: ServiceNow Business Hours Urgency.
  - `business_hours_impact`: ServiceNow Business Hours Impact.

  
## Usage

1. Ensure that the script prerequisites are met, and the Environment file is correctly configured.

2. Test the script using Python:

   ```bash
   python jboss_check_script.py
   ```
To run on Linux create a bash script, eg:
```bash
#!/bin/bash
 
# Set the environment variable for COMPUTERNAME
export COMPUTERNAME=$(hostname -s | tr '[:lower:]' '[:upper:]')
 
# Run the Python script
python3 /opt/scripts/agfaeiserverutils/cspJbossAlerts/jboss-check.py
```

3. Monitor the console output for information about JBoss EAP events, health checks, and email notifications.

4. Install as a scheduled task to run at server boot, script checks logs every 30 seconds by default. This script is to be installed on every Core Server in the cluster. Example: schtasks /create /ru "NT AUTHORITY\SYSTEM" /sc ONSTART /tr "'C:\Program Files\Python311\python.exe' E:\software\agfa-ei-jboss-alerts\jboss-check.py" /tn "Check Jboss Status"

 
# Xero Ticket Management Script

This script automates the management of Xero tickets by interacting with the Xero API, performing server actions, and creating incidents in ServiceNow based on specific conditions.

- SSH key generated on server script will be ran on
- SSH key imported onto all xero servers for agfaservice user
- SUDO permissions granted to the agfaservice user for the jboss and haproxy start/stop commands

## Configuration

The script uses a Environment file named `xeroticket.env` to store various parameters. Ensure that this file is present in the same directory as the script. Example Environment parameters include:

- Xero API Variables
- EI Cluster DB Variables
- Email Variables
- ServiceNow Variables

## Logging

The script logs its activities to a file named `xero_ticket.log` using the `logging` module. This log file can be referenced for debugging and auditing purposes.

## Usage

Run the script using the following command:

```bash
python xero_ticket_script.py
```

To run on Linux create a bash script, eg:
```bash
#!/bin/bash
 
# Set the environment variable for COMPUTERNAME
export COMPUTERNAME=$(hostname -s | tr '[:lower:]' '[:upper:]')
 
# Run the Python script
python3 /opt/scripts/agfaeiserverutils/xeroMonitoring/xeroticket.py
```

The script performs the following actions:

1. **Xero Ticket Creation**: Obtains a ticket from the Xero API for each specified Xero server.

2. **Ticket Verification**: Verifies the obtained ticket's validity by making a request to the Xero server.

3. **Server Actions**: Depending on the verification result, the script may restart or disable the Xero server.

4. **Incident Creation in ServiceNow**: In case of server actions, incidents are created in ServiceNow, and email notifications are sent.

5. **Disabled Server Awareness**: In the event a server is disabled by the script, it will be stored in the disabled_servers.txt file, after the server issues have been resolved, it will automatically removed from this file.

6. **Active Upgrade Awareness**: In the event the cluster is in a PREPARE status, the restart logic will be ignored, and an email notification will be sent if there is a failure, once the failed server passes valication, it will be removed from the disabled servers list and notification sent.

## Script Logic

The script is structured as follows:

- **Xero Ticket Management**: Obtains, verifies, and manages Xero tickets for specified servers.
- **Remote Server Actions**: Restarts or disables Xero servers based on verification results.
- **ServiceNow Integration**: Creates incidents in ServiceNow based on server actions.
- **Logging**: Captures activities and errors in the `xero_ticket.log` file.

## Error Handling

The script includes error handling for various scenarios, such as authentication failures, SSH connection errors, and ticket verification failures.

## Support and Issues

For any issues or questions, please create an issue in the [GitHub repository](https://github.com/mrjmc99/agfaeiserverutils/issues).