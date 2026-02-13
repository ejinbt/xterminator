# Data Usage Analysis - Twitter Monitoring Bot

## Scenario: 250 Coins/Day (Worst Case)

### Current Configuration
- **Initial Scan**: 500 tweets per coin
- **Monitoring Duration**: 3 hours per coin
- **Polling Interval**: Every 15 minutes (12 polls total)
- **Tweets per Poll**: 50 tweets
- **Total Tweets per Coin**: 500 + (12 × 50) = **1,100 tweets**

---

## Data Transfer Breakdown

### Per Tweet Response Size
Even though we're **only counting** (not storing content), we still receive full tweet JSON objects:

| Component | Size (bytes) | Notes |
|-----------|-------------|-------|
| Tweet JSON | 500-2,000 | Includes text, user info, engagement counts, URLs |
| User Object | 200-500 | Username, verified status, profile info |
| HTTP Headers | ~500 | Request/response headers |
| API Overhead | ~200 | Metadata, pagination tokens |
| **Average per Tweet** | **~1,500 bytes** | **~1.5 KB** |

### Daily Data Usage Calculation

```
250 coins/day × 1,100 tweets/coin × 1.5 KB/tweet = 412.5 MB/day
```

**Plus additional overhead:**
- HTTP connection overhead: ~10 MB
- Retry attempts (on errors): ~20 MB
- API metadata/pagination: ~15 MB
- Proxy overhead: ~5 MB

---

## **Total Estimated Data Usage**

### Worst Case Scenario
**~450-500 MB per day** (0.45-0.5 GB/day)

### Monthly Estimate
- **15 GB/month** (worst case)
- **10-12 GB/month** (average case)

---

## Cost Comparison

### Option 1: External Proxy (Bright Data / Similar)
- **Data Transfer Cost**: ~$0.10-0.15 per GB
- **Monthly Cost**: $1.50-2.25/month for data
- **Plus**: Proxy subscription ($500-1000/month for residential proxies)

### Option 2: Direct Connection (No Proxy)
- **Data Transfer**: Included in internet plan
- **Risk**: Higher chance of IP ban/rate limits
- **Cost**: $0 (but may need multiple IPs/VPS)

### Option 3: Optimized Approach
**Reduce data usage by:**
1. **Lower initial scan**: 500 → 200 tweets (-60% data)
2. **Fewer polls**: 12 → 6 polls (every 30 min) (-50% data)
3. **Smaller poll size**: 50 → 25 tweets (-50% data)

**Optimized Total**: ~100-150 MB/day (3-4.5 GB/month)

---

## Recommendations

### For 250 Coins/Day:

1. **If using proxy**: 
   - Data cost is **negligible** ($1.50-2.25/month)
   - Main cost is **proxy subscription** ($500-1000/month)
   - **Total**: ~$500-1000/month

2. **If direct connection**:
   - Data usage: **Free** (included in internet)
   - Risk: Need multiple IPs/VPS to avoid bans
   - **Total**: $20-50/month (VPS costs)

3. **Optimized version**:
   - Reduces data by **70%**
   - Still accurate for counting
   - **Best balance** of cost/accuracy

---

## Data Usage Breakdown Table

| Metric | Per Coin | 250 Coins/Day | Monthly |
|--------|----------|---------------|---------|
| Initial Scan | 500 tweets | 125,000 tweets | 3.75M tweets |
| Polling (12×) | 600 tweets | 150,000 tweets | 4.5M tweets |
| **Total Tweets** | **1,100** | **275,000** | **8.25M** |
| **Data Transfer** | **~1.65 MB** | **~412 MB** | **~12.4 GB** |

---

## Notes

- **Actual usage may vary** based on:
  - Tweet content length (longer tweets = more data)
  - Number of retweets/quotes (more nested objects)
  - API response format changes
  - Network overhead

- **Counting-only** still requires receiving full tweet objects to:
  - Check verified status
  - Count engagement metrics
  - Deduplicate tweets
  - Track tweet IDs

- **Storage** (if enabled) would add minimal overhead (~10-20% more) since we're already receiving the data
