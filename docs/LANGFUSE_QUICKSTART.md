# 🚀 Langfuse Quick Start Guide

## What is Langfuse?

Langfuse is an **LLM observability platform** that allows you to:
- 💰 **Track costs** per user, session, and operation
- 📊 **Monitor tokens** (input/output) in each call
- ⚡ **Measure latency** and agent performance
- 🐛 **Debug complete traces** with the full TAO flow
- 📈 **Analyze trends** in usage and costs

---

## 📋 Installation Steps (5 minutes)

### 1. Sign up for Langfuse Cloud (Free)

```bash
# Open in your browser:
https://cloud.langfuse.com/auth/sign-up

# ✅ No credit card required
# ✅ 50,000 events/month free
# ✅ 30 days data retention
```

### 2. Create Project

1. Once inside, click **"New Project"**
2. Name: `Smart Scout`
3. Region: EU (if you're in Europe)

### 3. Get API Keys

1. Go to **Settings** → **API Keys**
2. Click **"Create new API key pair"**
3. Copy both keys:
   - `Public Key` (pk-lf-...)
   - `Secret Key` (sk-lf-...)

### 4. Configure Environment Variables

Add these lines to your `.env` file:

```bash
# Langfuse Configuration
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_ENABLED=true
```

### 5. Install Dependency

```bash
# Already in pyproject.toml, just run:
pip install langfuse
# or if using uv:
uv pip install langfuse
```

### 6. Restart Services

```bash
docker-compose restart api
```

### 7. Verify Installation

```bash
python scripts/test_langfuse.py
```

If everything is working, you should see:
```
✅ LANGFUSE_PUBLIC_KEY: pk-lf-...
✅ LANGFUSE_SECRET_KEY: sk-lf-...
✅ Langfuse package imported successfully
✅ LLM provider initialized successfully
✅ Langfuse callback is registered
🎉 All tests passed!
```

---

## 🧪 Test the Integration

### Option A: From the Web Application

1. Open your browser: `http://localhost:8000`
2. Log in with your user
3. Go to **"Search Players"** and search for a similar player
4. Wait for the agent to respond

### Option B: From the API (cURL)

```bash
curl -X POST http://localhost:8001/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Find players similar to Pedri",
    "user_id": "test_user",
    "session_id": "test_session_001"
  }'
```

### Option C: From Python

```python
import requests

response = requests.post(
    "http://localhost:8001/chat/",
    json={
        "message": "Find players similar to Pedri",
        "user_id": "test_user",
        "session_id": "test_session_001"
    }
)

print(response.json())
```

---

## 📊 View Traces in Langfuse

1. Go to: https://cloud.langfuse.com
2. Select your project **"Smart Scout"**
3. Click **"Traces"** in the sidebar
4. You should see your recent trace

### Example Trace:

```
📊 Trace: "Find players similar to Pedri"
├─ User ID: test_user
├─ Session ID: test_session_001
├─ Total Cost: $0.045
├─ Total Tokens: 4,200
├─ Duration: 3.8s
│
├─ 🧠 LLM Call 1: System + User Message
│  ├─ Input Tokens: 1,250
│  ├─ Output Tokens: 150
│  ├─ Cost: $0.014
│  └─ Latency: 1.2s
│
├─ 🔧 Tool: player_lookup("Pedri")
│  └─ Latency: 0.3s
│
├─ 🔧 Tool: similar_players_team_fit_table(...)
│  └─ Latency: 1.5s
│
└─ 🧠 LLM Call 2: Format Response
   ├─ Input Tokens: 2,800
   ├─ Output Tokens: 450
   ├─ Cost: $0.031
   └─ Latency: 1.8s
```

---

## 💰 Monitor Costs

### Cost Dashboard

1. In Langfuse, go to **"Dashboard"**
2. You'll see real-time metrics:
   - **Total Cost Today**: Accumulated cost for the day
   - **Tokens Used**: Total tokens (input + output)
   - **Average Latency**: Average response latency
   - **Request Count**: Number of requests

### Costs per User

1. Go to **"Users"** in the sidebar
2. You'll see a table with:
   - User ID
   - Total requests
   - Total cost
   - Average cost per request

### Costs per Operation

Filter traces by tags:
- `operation:search` → Player searches
- `operation:dashboard` → Dashboard generation
- `operation:pdf` → PDF report creation

---

## 🔔 Configure Alerts

### Daily Cost Alert

1. Go to **Settings** → **Alerts**
2. Click **"Create Alert"**
3. Configure:
   - **Type**: Daily Cost Threshold
   - **Threshold**: $50.00 (adjust to your budget)
   - **Notification**: Email
4. Save

You'll receive an email if daily cost exceeds the threshold.

---

## 📈 Recommended Dashboards

### 1. Cost Overview

Metrics:
- Total cost today/week/month
- Cost trend (line chart)
- Top 5 most expensive operations
- Cost per user (pie chart)

### 2. Performance Monitoring

Metrics:
- Average latency (p50, p95, p99)
- Slowest endpoints
- Error rate over time
- Success rate by operation

### 3. User Analytics

Metrics:
- Most active users
- Cost per user
- Sessions per user
- Average tokens per user

---

## 🐛 Debugging with Langfuse

### View Complete Trace

When something fails or you want to analyze a conversation:

1. Go to **Traces** → search by `session_id` or `user_id`
2. Click on the trace
3. You'll see:
   - **Timeline**: All steps in chronological order
   - **LLM Calls**: Input/output of each model call
   - **Tool Executions**: Which tools were used
   - **Metadata**: user_id, session_id, tags
   - **Errors**: Stack trace if there was an error

### Search for Errors

1. Go to **Traces**
2. Filter by: `status:error`
3. You'll see all failed traces
4. Click on one to see the complete stack trace

---

## 🔧 Troubleshooting

### ❌ "Langfuse package not installed"

```bash
pip install langfuse
# or
uv pip install langfuse
```

### ❌ "Langfuse tracking disabled (missing API keys)"

Verify that variables are in your `.env`:
```bash
cat .env | grep LANGFUSE
```

You should see:
```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

### ❌ "Error initializing Langfuse: Invalid API key"

1. Go to Langfuse Dashboard → Settings → API Keys
2. Verify that the keys are correct
3. If you regenerated them, update your `.env`
4. Restart services: `docker-compose restart api`

### ❌ I don't see traces in Langfuse

1. Verify that `LANGFUSE_ENABLED=true` in your `.env`
2. Check API service logs:
   ```bash
   docker-compose logs -f api | grep Langfuse
   ```
3. You should see: `✅ Langfuse tracking enabled for user: ...`

---

## 📊 Cost Projection

### With 100 active users/day:

| Operation | Uses/day | Cost/operation | Cost/day |
|-----------|----------|----------------|----------|
| Similar search | 200 | $0.04 | $8.00 |
| Dashboard | 100 | $0.02 | $2.00 |
| PDF Report | 50 | $0.10 | $5.00 |
| Simple chat | 300 | $0.01 | $3.00 |
| **TOTAL** | **650** | - | **$18/day** |

**Monthly cost: ~$540** (30 days × $18)

### Optimization:

- **Reduce context**: Shorten system prompts
- **Cache embeddings**: Reuse embeddings from similar searches
- **Cheaper model**: Use GPT-4o-mini for simple operations
- **Batching**: Group multiple requests

---

## 🔐 Security

⚠️ **IMPORTANT**:

1. **NEVER** commit API keys to GitHub
2. Add `.env` to `.gitignore` (already done)
3. Rotate keys if you believe they were compromised:
   - Langfuse Dashboard → Settings → API Keys → "Revoke"
4. Use environment variables in production
5. Restrict Langfuse project access to your team only

---

## 📞 Support

- **Official Documentation**: https://langfuse.com/docs
- **Community Discord**: https://discord.gg/7NXusRtqYU
- **GitHub Issues**: https://github.com/langfuse/langfuse/issues

---

## ✅ Checklist

- [ ] Registered in Langfuse Cloud
- [ ] "Smart Scout" project created
- [ ] API keys copied
- [ ] Variables added to `.env`
- [ ] Dependency installed: `pip install langfuse`
- [ ] Services restarted: `docker-compose restart api`
- [ ] Test executed: `python scripts/test_langfuse.py`
- [ ] First trace visible in Langfuse Dashboard
- [ ] Cost alert configured
- [ ] Custom dashboard created

---

Done! Now you have complete visibility of costs and performance of your LLM agent. 🎉
