# Langfuse Setup Guide

## 🎯 Objective

Integrate **Langfuse** for cost tracking, token monitoring, and performance analysis of the LLM agent in Smart Scout.

---

## 📋 Required Environment Variables

Add these variables to your `.env` file:

```bash
# -----------------------------------------------------------------------------
# Langfuse Configuration (LLM Observability & Cost Tracking)
# -----------------------------------------------------------------------------
# Sign up at https://cloud.langfuse.com/auth/sign-up
# Go to Settings → API Keys to get your keys

LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com

# Optional: Enable/disable Langfuse tracking (useful for local dev)
LANGFUSE_ENABLED=true

# Optional: Set daily cost alert threshold in USD
LANGFUSE_DAILY_COST_ALERT=50.00
```

---

## 🔑 Obtaining API Keys

### Step 1: Sign up for Langfuse Cloud (Free)

1. Go to: https://cloud.langfuse.com/auth/sign-up
2. Sign up with your email (no credit card required)
3. Confirm your email

### Step 2: Create a Project

1. Once logged in, create a new project: **"Smart Scout"**
2. Select region (recommended: EU if you're in Europe)

### Step 3: Get API Keys

1. Go to **Settings** → **API Keys**
2. Click **"Create new API key pair"**
3. Copy both keys:
   - **Public Key** (pk-lf-...)
   - **Secret Key** (sk-lf-...)
4. Paste them into your `.env` file

---

## 🆓 Free Plan - Limits

- ✅ **50,000 events/month** (sufficient for development and testing)
- ✅ **Complete tracking**: LLM calls, tool calls, costs, latency
- ✅ **Interactive dashboard**
- ✅ **Data retention: 30 days**
- ✅ **No credit card required**

### What counts as an "event"?

- 1 LLM call = 1 event
- 1 tool execution = 1 event
- 1 complete user trace = multiple events

**Example**: A similar player search generates ~5-8 events.

---

## 📊 Tracked Metrics

### 1. Costs
- Total cost per day/week/month
- Cost per user
- Cost per operation type (search, dashboard, PDF)
- Breakdown by model (GPT-4, GPT-3.5, embeddings)

### 2. Tokens
- Input tokens (prompts + context)
- Output tokens (generated responses)
- Total tokens per session/user

### 3. Latency
- Agent response time
- Time per tool call
- Percentiles (p50, p95, p99)

### 4. Traceability
- Complete TAO flow (Think-Action-Observation)
- Tools executed in each conversation
- Errors and exceptions with stack trace

---

## 🔔 Cost Alerts

You can configure alerts in Langfuse for:

- **Daily cost threshold**: Alert if daily cost exceeds $X
- **Per-user cost threshold**: Alert if a user spends more than $Y
- **Token usage spike**: Alert for unusual usage spikes

### Configuring Alerts:

1. In Langfuse Dashboard → **Settings** → **Alerts**
2. **Create Alert**:
   - **Type**: Daily Cost
   - **Threshold**: $50.00 (or your preferred value)
   - **Notification**: Email
3. Save

---

## 💰 Cost Projection

### Scenario: 100 active users/day

| Operation | Uses/day | Tokens/action | Cost/action | Total Cost/day |
|-----------|----------|---------------|-------------|----------------|
| Similar search | 200 | 4,000 | $0.04 | $8.00 |
| Dashboard inline | 100 | 2,000 | $0.02 | $2.00 |
| PDF Report | 50 | 10,000 | $0.10 | $5.00 |
| Simple chat | 300 | 1,000 | $0.01 | $3.00 |
| **TOTAL** | **650** | - | - | **$18.00/day** |

**Estimated monthly cost: ~$540** (with 100 active users/day)

---

## 🐛 Debugging with Langfuse

### View Complete Trace

When something fails or you want to analyze a conversation:

1. Go to **Langfuse Dashboard** → **Traces**
2. Filter by:
   - **User ID**: To see all operations from a user
   - **Session ID**: To view a specific session
   - **Date Range**: For temporal analysis
3. Click on a trace to see:
   - All LLM calls
   - All tool executions
   - Input/output of each step
   - Latency of each component
   - Stack trace if there was an error

### Trace Example:

```
📊 Trace: "Find players similar to Pedri for Barcelona"
├─ 🧠 LLM Call 1: Understand intent
│  ├─ Input: 1,250 tokens → $0.0125
│  └─ Output: 150 tokens → $0.0015
│  └─ Latency: 1.2s
│
├─ 🔧 Tool: player_lookup("Pedri")
│  └─ Latency: 0.3s
│
├─ 🔧 Tool: similar_players_team_fit_table(...)
│  └─ Latency: 1.5s
│
├─ 🧠 LLM Call 2: Format response
│  ├─ Input: 2,800 tokens → $0.028
│  └─ Output: 450 tokens → $0.0045
│  └─ Latency: 1.8s
│
└─ 📊 Total:
   ├─ Tokens: 4,650
   ├─ Cost: $0.0465
   └─ Latency: 4.8s
```

---

## 🔧 Local Testing

To test without sending data to Langfuse during development:

```bash
# In your local .env
LANGFUSE_ENABLED=false
```

This disables tracking, useful when debugging locally.

---

## 📈 Recommended Dashboards

In Langfuse, create these dashboards:

### 1. **Daily Overview**
- Total cost today
- Total tokens today
- Number of requests
- Average latency

### 2. **User Analysis**
- Top 10 users by cost
- Top 10 users by requests
- Cost per user (histogram)

### 3. **Operation Breakdown**
- Cost by operation type (search, dashboard, PDF)
- Most used tools
- Success rate per operation

### 4. **Performance**
- Latency p50, p95, p99
- Slowest operations
- Error rate over time

---

## ✅ Post-Installation Checklist

- [ ] Registration completed in Langfuse Cloud
- [ ] API keys copied to `.env`
- [ ] `LANGFUSE_*` variables configured
- [ ] Docker services restarted: `docker-compose restart api`
- [ ] Test search performed in the app
- [ ] Trace appears in Langfuse Dashboard
- [ ] Daily cost alert configured
- [ ] Custom dashboards created

---

## 📞 Support

- **Official Documentation**: https://langfuse.com/docs
- **Community Discord**: https://discord.gg/7NXusRtqYU
- **GitHub**: https://github.com/langfuse/langfuse

---

## 🔐 Security

⚠️ **IMPORTANT**: 
- Langfuse API keys have full access to your project
- **NEVER** commit them to GitHub
- Always use environment variables
- Rotate keys if you believe they've been compromised
