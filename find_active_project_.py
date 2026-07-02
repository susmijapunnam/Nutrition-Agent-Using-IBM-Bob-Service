"""
find_active_project.py — Finds which of your projects has an active WML instance.
Run: python find_active_project.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()
import os, requests

API_KEY = os.getenv("IBM_API_KEY", "")
WX_URL  = os.getenv("IBM_WATSONX_URL", "")
MODEL_ID = os.getenv("WATSONX_MODEL_ID", "")

# Get IAM token
token_res = requests.post(
    "https://iam.cloud.ibm.com/identity/token",
    data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": API_KEY},
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)
token = token_res.json().get("access_token", "")
print("IAM token OK\n")

# All 5 projects from your account
PROJECTS = [
    ("prompt lab",                  "62911d14-7726-475f-ad31-2a41e52e9b8c"),
    ("punnam's sandbox",            "9e58caab-1b6e-4a73-92d9-c68036b2d79a"),
    ("Jupyter",                     "fcb37dd9-dff3-4cbb-a980-8f1e53136a63"),
    ("Predictive Maintenance 1",    "907dd2fc-3435-4f87-b5d3-819f400707c7"),
    ("Predictive Maintenance 2",    "10adb4d0-724c-464e-b576-acec90655bc5"),
]

from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as Params

creds = Credentials(url=WX_URL, api_key=API_KEY)

WORKING_PROJECT = None

for name, pid in PROJECTS:
    print(f"Testing: '{name}' ({pid[:8]}...)  ", end="", flush=True)
    try:
        model = ModelInference(
            model_id    = MODEL_ID,
            credentials = creds,
            project_id  = pid,
            params      = {Params.MAX_NEW_TOKENS: 20, Params.TEMPERATURE: 0.5},
        )
        result = model.generate_text(prompt="### Assistant\nHello")
        print(f"ACTIVE! Response: {result.strip()[:60]}")
        WORKING_PROJECT = (name, pid)
        break
    except Exception as e:
        err = str(e)
        if "Inactive" in err:
            print("INACTIVE (WML suspended)")
        elif "not supported" in err:
            print("MODEL NOT SUPPORTED in this project")
        elif "not_found" in err or "404" in err:
            print("PROJECT NOT FOUND")
        else:
            print(f"ERROR: {err[:80]}")

print()
if WORKING_PROJECT:
    print("=" * 55)
    print(f"WORKING PROJECT FOUND!")
    print(f"  Name : {WORKING_PROJECT[0]}")
    print(f"  ID   : {WORKING_PROJECT[1]}")
    print("=" * 55)
    print(f"\nUpdate .env with: IBM_PROJECT_ID={WORKING_PROJECT[1]}")
else:
    print("No active project found with this model.")
    print("The WML instance needs to be reactivated on IBM Cloud.")
