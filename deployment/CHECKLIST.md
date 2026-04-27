# Pre-Deployment Checklist

Use this checklist before deploying **smart-bidi-3** to Google Cloud Run.

---

## Prerequisites

-[ ] **Google Cloud SDK installed**
  -Test: `gcloud --version`
  -Install: https://cloud.google.com/sdk/docs/install

-[ ] **Authenticated with Google Cloud**
  -Test: `gcloud auth list`
  -Login: `gcloud auth login`

-[ ] **GCP Project exists with billing enabled**
  -Test: `gcloud projects list`
  -Set: `gcloud config set project YOUR_PROJECT_ID`

-[ ] **Google Gemini API Key obtained**
  -Get: https://aistudio.google.com/app/apikey
  -Save it -you'll need it during deployment

---

## Code Ready

-[ ] **Latest code is saved**
  -All changes in `app/` folder saved
  -Telephony integration included (`app/telephony/`)

-[ ] **Dependencies updated** (if you added any)
  -Check: `../pyproject.toml` has all needed packages
  -Telnyx is already included: ✅

-[ ] **Environment tested locally** (optional but recommended)
  ```powershell
  cd ../app
  uv run python main.py
  ```
  -Browser works: http://localhost:8000
  -WebSocket connects

---

## Deployment Configuration

Review these settings in `deploy.ps1`:

-[ ] **Service Name**: `smart-bidi-3` ✅ (correct, won't interfere)
-[ ] **Region**: `us-central1` (or change with `-Region` parameter)
-[ ] **Memory**: 2GB ✅ (sufficient for AI workloads)
-[ ] **CPU**: 2 vCPUs ✅ (handles concurrent requests)
-[ ] **Timeout**: 3600s ✅ (1 hour for long calls)
-[ ] **Scaling**: 0-10 instances ✅ (cost-effective)

---

## Ready to Deploy

### Execute Deployment

```powershell
cd C:\code\canadapost\voice3\smart-shipping-bidi-II\deployment
.\deploy.ps1
```

### During Deployment

The script will:
1. Ask for Google API Key (paste when prompted)
2. Copy files from parent directory
3. Enable required GCP APIs (takes ~30 seconds)
4. Build Docker container (takes ~3-5 minutes)
5. Deploy to Cloud Run (takes ~1 minute)
6. Return public HTTPS URL

**Total time**: ~5-7 minutes

---

## Post-Deployment Verification

After deployment succeeds:

### 1. Test Web Interface

-[ ] **Open Cloud Run URL in browser**
  -URL format: `https://smart-bidi-3-xxxxx-uc.a.run.app`
  -Should load the SmartShip UI

-[ ] **Test voice chat**
  -Click microphone icon
  -Allow browser microphone access
  -Speak to the AI assistant
  -Verify responses work

### 2. Test texml Endpoint

```powershell
curl https://smart-bidi-3-xxxxx-uc.a.run.app/texml/voice
```

Expected output:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Connecting you to Smart Ship Assistant</Say>
    <Connect>
        <Stream url="wss://smart-bidi-3-xxxxx-uc.a.run.app/ws/phone/{{CallSid}}" />
    </Connect>
</Response>
```

### 3. Configure Telnyx (If using phone integration)

-[ ] **Copy your Cloud Run URL**
-[ ] **Go to Telnyx Console**: https://console.Telnyx.com/us1/develop/phone-numbers/manage/incoming
-[ ] **Select your phone number**
-[ ] **Configure webhook**:
  -Webhook URL: `https://smart-bidi-3-xxxxx-uc.a.run.app/texml/voice`
  -HTTP Method: POST
-[ ] **Save configuration**
-[ ] **Call your Telnyx number** -AI should answer!

### 4. Monitor Logs

```bash
gcloud run logs tail smart-bidi-3 --region=us-central1
```

Watch for:
-✅ Startup messages
-✅ Incoming requests
-✅ WebSocket connections
-❌ Any error messages

---

## Troubleshooting

### Issue: "Project not found"
```bash
gcloud config set project YOUR_PROJECT_ID
gcloud config list
```

### Issue: "API not enabled"
```bash
gcloud services enable run.googleapis.com --project=YOUR_PROJECT_ID
gcloud services enable cloudbuild.googleapis.com --project=YOUR_PROJECT_ID
```

### Issue: "Permission denied"
```bash
# Verify you're authenticated
gcloud auth list

# Re-authenticate if needed
gcloud auth login
```

### Issue: "Deployment times out"
-Check internet connection
-Try again: `.\deploy.ps1`
-Check Cloud Build status: https://console.cloud.google.com/cloud-build

### Issue: "Phone calls drop immediately"
-Verify webhook URL is exact with `/texml/voice`
-Check Cloud Run timeout is 3600s (already configured)
-View logs: `gcloud run logs read smart-bidi-3 --limit=50`
-Test texml endpoint with curl

---

## Success Criteria

Deployment is successful when:

-✅ `deploy.ps1` completes without errors
-✅ Cloud Run URL is accessible in browser
-✅ Web voice chat works (microphone → AI response)
-✅ texml endpoint returns valid XML
-✅ (Optional) Phone calls connect to AI assistant
-✅ Logs show no errors

---

## Quick Commands Reference

```bash
# Deploy
.\deploy.ps1

# View logs
gcloud run logs tail smart-bidi-3 --region=us-central1

# Check status
gcloud run services describe smart-bidi-3 --region=us-central1

# List all services
gcloud run services list --project=YOUR_PROJECT_ID

# Delete service (if needed)
gcloud run services delete smart-bidi-3 --region=us-central1

# Update deployment
.\deploy.ps1  # Same command
```

---

## You're Ready!

If all items above are checked, you're ready to deploy:

```powershell
cd C:\code\canadapost\voice3\smart-shipping-bidi-II\deployment
.\deploy.ps1
```

Good luck! 🚀

