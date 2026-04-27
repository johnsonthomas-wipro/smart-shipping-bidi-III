# Quick Deployment Guide - smart-bidi-3

## Deploy in 2 Minutes

### 1. Deploy to Google Cloud Run

```powershell
cd deployment
.\deploy.ps1
```

**You'll be prompted for:**
- Google API Key ([get here](https://aistudio.google.com/app/apikey))

**Script will automatically:**
- Copy latest code
- Enable GCP APIs
- Build Docker container
- Deploy as **smart-bidi-3**
- Return public HTTPS URL

---

### 2. Configure Telnyx (Optional - for phone calls)

After deployment completes, copy your Cloud Run URL:

```
https://smart-bidi-3-xxxxx-uc.a.run.app
```

Then:
1. Go to [Telnyx Portal → Numbers](https://portal.telnyx.com/#/app/numbers)
2. Select your phone number
3. Under "Voice Settings":
   - **Connection Type**: TeXML Application
   - Create new TeXML Application or select existing
4. In TeXML Application settings:
   - **Webhook URL**: `https://smart-bidi-3-xxxxx-uc.a.run.app/texml/voice`
   - **HTTP Method**: POST or GET
5. Save

**That's it!** Call your Telnyx number to talk to the AI assistant.

---

## 🔄 Update Deployment

```powershell
cd deployment
.\deploy.ps1
```

Same command - Cloud Run handles updates automatically with zero downtime.

---

## Test Locally First

```powershell
# Build Docker image
.\build.ps1

# Run locally
docker run -p 8080:8080 -e GOOGLE_API_KEY="your-key" smart-bidi-3:latest

# Open browser
http://localhost:8080
```

---

## Monitor Your Deployment

```bash
# View live logs
gcloud run logs tail smart-bidi-3 --region=us-central1

# Check service status
gcloud run services describe smart-bidi-3 --region=us-central1

# List all services
gcloud run services list
```

---

## Common Issues

### "Project not found"
```bash
gcloud config set project YOUR_PROJECT_ID
```

### "API not enabled"
```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

### "Telnyx calls drop after greeting"
- Check Cloud Run timeout is >= 3600s (default in deploy.ps1)
- Verify webhook URL is exact: `https://your-url/texml/voice`
- Check logs: `gcloud run logs tail smart-bidi-3`

---

## Pro Tips

- **Cost**: Service scales to zero when not in use = $0 idle cost
- **Updates**: Just run `.\deploy.ps1` again to deploy changes
- **Regions**: Use `-Region "us-east1"` for different region
- **Multiple environments**: Change `-ServiceName` for dev/staging/prod

---

## Endpoints

Once deployed, your service exposes:

- `GET /` - Web UI for browser-based voice chat
- `POST /texml/voice` - Telnyx webhook (returns TeXML)
- `WS /ws/phone` - Telnyx WebSocket for phone calls
- `WS /ws/{user_id}` - Browser WebSocket for ADK streaming

---

## Environment Variables

Set during deployment:
- `GOOGLE_API_KEY` - Your Gemini API key
- `PORT=8080` - Cloud Run standard port
- `SHOW_CONVERSATION=no` - Hide debug output

---

For detailed information, see [README.md](README.md)
