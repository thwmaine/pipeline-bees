from airflow import DAG
from airflow.utils.dates import days_ago
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
import requests
import time

DATABRICKS_INSTANCE = "https://<seu-workspace>.azuredatabricks.net"  # ex: https://adb-1234567890.10.azuredatabricks.net
DATABRICKS_TOKEN = "{{ var.value.DATABRICKS_TOKEN }}"  # setar no Airflow UI > Admin > Variables
JOB_ID = 162772105190215

default_args = {
    "owner": "fernanda",
    "depends_on_past": False,
    "email": ["emaildepreferencia@ambev.com"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": 300,  # 5 minutos
}

def trigger_databricks_job(**context):
    url = f"{DATABRICKS_INSTANCE}/api/2.1/jobs/run-now"
    headers = {
        "Authorization": f"Bearer {DATABRICKS_TOKEN}"
    }
    payload = {
        "job_id": JOB_ID
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    run_id = response.json().get("run_id")
    if not run_id:
        raise Exception("No run_id returned from Databricks API")
    context['ti'].xcom_push(key='run_id', value=run_id)

def wait_for_job_finish(**context):
    run_id = context['ti'].xcom_pull(key='run_id')
    url = f"{DATABRICKS_INSTANCE}/api/2.1/jobs/runs/get"
    headers = {
        "Authorization": f"Bearer {DATABRICKS_TOKEN}"
    }
    while True:
        response = requests.get(url, params={"run_id": run_id}, headers=headers)
        response.raise_for_status()
        run_state = response.json().get("state", {})
        life_cycle_state = run_state.get("life_cycle_state")
        result_state = run_state.get("result_state")
        if life_cycle_state in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            if result_state == "SUCCESS":
                print("Job finished successfully")
                return
            else:
                raise Exception(f"Databricks job failed with result_state: {result_state}")
        print("Job still running... waiting 30s")
        time.sleep(30)

with DAG(
    dag_id="databricks_run_notebook",
    schedule_interval=None,
    start_date=days_ago(1),
    default_args=default_args,
    catchup=False,
) as dag:

    trigger_job = PythonOperator(
        task_id="trigger_databricks_job",
        python_callable=trigger_databricks_job,
        provide_context=True,
    )

    wait_for_job = PythonOperator(
        task_id="wait_for_databricks_job",
        python_callable=wait_for_job_finish,
        provide_context=True,
    )

    trigger_job >> wait_for_job