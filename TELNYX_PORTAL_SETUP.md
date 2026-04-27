# Telnyx Portal Configuration Guide

This guide explains what you need to configure in the Telnyx portal to make your SmartShip Voice Assistant work with phone calls.

## 📋 Prerequisites

Before starting, you need:
- ✅ Telnyx account (sign up at https://portal.telnyx.com)
- ✅ Your server running and accessible via HTTPS (required for WebSocket)
- ✅ Your server's public URL (e.g., `https://your-domain.com`)

## 🚀 Step-by-Step Configuration

### Step 1: Create Telnyx Account

1. Go to https://portal.telnyx.com
2. Sign up for an account (free trial available)
3. Verify your email
4. Add payment method (required even for trial)

### Step 2: Purchase a Phone Number

1. In Telnyx Portal, navigate to **Numbers → Search & Buy**
2. Select your country (e.g., Canada, United States)
3. Choose a phone number:
   - Local number: Specific area code
   - Toll-free: 1-800/1-888 numbers
   - Mobile: If available in your region
4. Click **Buy Now**
5. Complete the purchase

**Cost**: Typically $1-5/month depending on number type

### Step 3: Create TeXML Application

1. Navigate to **TeXML → Applications**
2. Click **Create New Application**
3. Configure the application:
   - **Application Name**: "SmartShip Voice Assistant" (or your choice)
   - **Webhook URL (Voice)**: `https://your-domain.com/texml/voice`
     - ⚠️ Replace `your-domain.com` with your actual domain
     - ⚠️ Must be HTTPS (not HTTP)
     - ⚠️ Must be publicly accessible
   - **HTTP Method**: POST (recommended) or GET
   - **Failover URL** (optional): Backup URL if main fails
4. Click **Save**

### Step 4: Link Phone Number to TeXML Application

1. Navigate to **Numbers → My Numbers**
2. Find the phone number you purchased
3. Click on the number to edit
4. Under **Voice Settings**:
   - **Connection Type**: Select "TeXML Application"
   - **TeXML Application**: Select the application you created in Step 3
5. Click **Save Changes**

### Step 5: Verify Configuration

1. Start your server:
   ```bash
   cd app
   python main.py
   ```

2. Make sure your server is accessible via HTTPS:
   - For local development: Use ngrok or VS Code port forwarding
   - For production: Deploy to cloud (Azure, GCP, AWS)

3. Test the webhook endpoint:
   ```bash
   curl https://your-domain.com/texml/voice
   ```
   Should return TeXML:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <Response>
       <Say voice="alice">Connecting you to Smart Ship Assistant</Say>
       <Stream url="wss://your-domain.com/ws/phone" />
   </Response>
   ```

4. Call your Telnyx number from any phone
5. You should hear: "Connecting you to Smart Ship Assistant"
6. The call should connect to the AI assistant
7. Check your server logs for connection confirmation

## 🔍 What Happens When Someone Calls

```
1. User dials your Telnyx number
   ↓
2. Telnyx receives the call
   ↓
3. Telnyx sends HTTP request to: https://your-domain.com/texml/voice
   ↓
4. Your server returns TeXML with:
   - Greeting: "Connecting you to Smart Ship Assistant"
   - WebSocket URL: wss://your-domain.com/ws/phone
   ↓
5. Telnyx plays greeting to caller
   ↓
6. Telnyx opens WebSocket connection to your server
   ↓
7. Your server creates IVR agent session
   ↓
8. Bidirectional audio streaming begins:
   - Caller audio → Telnyx → Your Server → Gemini ADK
   - Gemini response → Your Server → Telnyx → Caller
   ↓
9. Conversation continues until caller hangs up
   ↓
10. Server cleans up session
```

## 🌐 Local Development Setup (ngrok)

If testing locally, use ngrok to expose your local server:

```bash
# Install ngrok
# Download from https://ngrok.com/download

# Start your server
cd app
python main.py

# In another terminal, start ngrok
ngrok http 8000

# ngrok will give you a URL like:
# https://abc123.ngrok.io

# Use this URL in Telnyx:
# Webhook URL: https://abc123.ngrok.io/texml/voice
```

**Important**: ngrok URLs change each time you restart ngrok (unless you have a paid plan). You'll need to update the webhook URL in Telnyx each time.

## 🔧 Advanced Configuration (Optional)

### Call Recording

1. In Telnyx Portal → TeXML Application
2. Enable **Call Recording**
3. Configure storage location
4. Recordings will be available in Portal → Call Logs

### Call Analytics

1. Navigate to **Reports → Voice**
2. View call metrics:
   - Call duration
   - Call quality
   - Geographic distribution
   - Peak usage times

### Failover Configuration

Set up a backup webhook in case primary fails:

1. TeXML Application → Edit
2. **Failover URL**: `https://backup-domain.com/texml/voice`
3. **Failover Method**: POST
4. If primary URL fails, Telnyx will try failover

### SIP Configuration (Advanced)

For direct SIP integration instead of TeXML:

1. Navigate to **Voice → SIP Connections**
2. Create new SIP connection
3. Configure endpoint and credentials
4. More complex but offers lower latency

## 💰 Pricing

Typical Telnyx costs (as of 2026):

- **Phone Number**: $1-5/month
- **Inbound Calls**: $0.004-0.01/minute
- **Outbound Calls**: $0.01-0.02/minute (if needed)
- **SMS** (if added): $0.004/message

**Total estimated cost**: ~$5-20/month for moderate usage

## 🐛 Troubleshooting

### "Webhook returned error"

- ✅ Verify webhook URL is correct: `https://your-domain.com/texml/voice`
- ✅ Ensure URL is publicly accessible (test with curl)
- ✅ Check server logs for errors
- ✅ Verify HTTPS (not HTTP)

### "Call connects but no audio"

- ✅ Check WebSocket URL is accessible: `wss://your-domain.com/ws/phone`
- ✅ Verify server supports WebSocket connections
- ✅ Check for firewall blocking WebSocket
- ✅ Review server logs for audio transcoding errors

### "Call drops immediately"

- ✅ Ensure server timeout is >= 3600 seconds (1 hour)
- ✅ Check WebSocket connection is established
- ✅ Verify audio transcoding is working
- ✅ Review logs for exceptions

### "TeXML validation error"

- ✅ Check TeXML syntax in server response
- ✅ Ensure proper XML formatting
- ✅ Verify Stream URL is using `wss://` (not `ws://`)

## 📚 Additional Resources

- **Telnyx Documentation**: https://developers.telnyx.com/
- **TeXML Reference**: https://developers.telnyx.com/docs/api/v2/texml
- **Voice API Guide**: https://developers.telnyx.com/docs/v2/voice
- **WebSocket Streaming**: https://developers.telnyx.com/docs/v2/voice/streaming

## ✉️ Support

- **Telnyx Support**: support@telnyx.com
- **Portal Help**: Click "?" icon in Telnyx Portal
- **Community**: https://community.telnyx.com/

---

## 🎯 Quick Checklist

Before going live, verify:

- [ ] Telnyx account created
- [ ] Phone number purchased
- [ ] TeXML Application created
- [ ] Webhook URL configured (HTTPS)
- [ ] Phone number linked to TeXML Application
- [ ] Server running and accessible
- [ ] Test call successful
- [ ] Audio quality is good
- [ ] Server logs show no errors
- [ ] Environment variables configured (GOOGLE_API_KEY)

Once all items are checked, you're ready for production! 🚀
