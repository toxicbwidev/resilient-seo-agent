"""Bedrock access diagnostic. Reads credentials from CSV, runs 4 probes."""
import csv
import json
import os
import sys

CSV_PATH = os.path.join(os.path.dirname(__file__), "truefoundry-bedrock_accessKeys.csv")

with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    row = next(csv.DictReader(f))
    os.environ["AWS_ACCESS_KEY_ID"] = row["Access key ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = row["Secret access key"]
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

import boto3
from botocore.exceptions import ClientError, BotoCoreError

def banner(s):
    print("\n" + "=" * 60)
    print(f"  {s}")
    print("=" * 60)

banner("PROBE 1: STS get-caller-identity (IAM works?)")
try:
    sts = boto3.client("sts")
    ident = sts.get_caller_identity()
    print(f"OK Account: {ident['Account']}  Arn: {ident['Arn']}")
except (ClientError, BotoCoreError) as e:
    print(f"FAIL: {e}")
    sys.exit(1)

banner("PROBE 2: bedrock list-foundation-models (service activated?)")
try:
    bedrock = boto3.client("bedrock", region_name="us-east-1")
    resp = bedrock.list_foundation_models()
    models = resp.get("modelSummaries", [])
    print(f"OK Got {len(models)} models. First 5:")
    for m in models[:5]:
        print(f"   - {m['modelId']}  ({m.get('providerName')})")
    print("   ...")
    interesting = [m for m in models if any(p in m["modelId"] for p in ("mistral.mistral-large", "anthropic.claude-sonnet-4", "meta.llama3-3-70b", "cohere.command-r-plus"))]
    print(f"\n   Interesting (Mistral Large / Claude Sonnet 4 / Llama 3.3 70B / Command R+): {len(interesting)}")
    for m in interesting:
        print(f"   - {m['modelId']}")
except (ClientError, BotoCoreError) as e:
    print(f"FAIL: {e}")

runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

def try_invoke(label, model_id, body):
    banner(f"PROBE: invoke {label}  ({model_id})")
    try:
        resp = runtime.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        payload = json.loads(resp["body"].read())
        print(f"OK Response: {payload}")
    except (ClientError, BotoCoreError) as e:
        print(f"FAIL: {type(e).__name__}: {e}")

claude_body = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 20,
    "messages": [{"role": "user", "content": "Reply with one word: working"}],
}

mistral_body = {
    "prompt": "<s>[INST] Reply with one word: working [/INST]",
    "max_tokens": 10,
    "temperature": 0.0,
}

try_invoke("Claude Sonnet 4.6 via US profile", "us.anthropic.claude-sonnet-4-6", claude_body)
try_invoke("Claude Sonnet 4.5 via US profile", "us.anthropic.claude-sonnet-4-5-20250929-v1:0", claude_body)

banner("PROBE: list inference profiles")
try:
    profiles = boto3.client("bedrock", region_name="us-east-1").list_inference_profiles()
    print(f"OK Got {len(profiles.get('inferenceProfileSummaries', []))} profiles. First 10:")
    for p in profiles.get('inferenceProfileSummaries', [])[:10]:
        print(f"   - {p.get('inferenceProfileId')}  status={p.get('status')}")
except (ClientError, BotoCoreError) as e:
    print(f"FAIL: {type(e).__name__}: {e}")

try_invoke("Mistral Large 3",        "mistral.mistral-large-3-675b-instruct", mistral_body)
try_invoke("Mistral Large 24.02",    "mistral.mistral-large-2402-v1:0",        mistral_body)
try_invoke("Claude Sonnet 4.6",      "anthropic.claude-sonnet-4-6",            claude_body)
try_invoke("Claude Sonnet 4.5",      "anthropic.claude-sonnet-4-5-20250929-v1:0", claude_body)
try_invoke("Claude Sonnet 4",        "anthropic.claude-sonnet-4-20250514-v1:0",   claude_body)
try_invoke("Cohere Command R+",      "cohere.command-r-plus-v1:0",
           {"message": "Reply with one word: working", "max_tokens": 10})
try_invoke("Llama 3.3 70B",          "meta.llama3-3-70b-instruct-v1:0",
           {"prompt": "Reply with one word: working", "max_gen_len": 10})

print("\n" + "=" * 60)
print("  Diagnostic complete.")
print("=" * 60)
