# Proxy Research for X/Twitter Scraping

BrightData failed. These are providers with proven track records for Twitter/X scraping.

---

## Category 1: Mobile 4G/5G Proxies (Highest Success Rate)

Mobile proxies use real carrier IPs shared by thousands of real users. Twitter treats these as legitimate.

### ProxyEmpire (TOP PICK)
- Pool: 5M+ mobile IPs, 170+ countries
- Pricing: ~$8-15/GB for mobile
- Sticky sessions: Yes
- Why: Best mobile pool, proven for social media scraping
- Website: proxyempire.io

### NodeMaven
- Pool: 30M+ IPs (residential + mobile)
- Pricing: ~$4/GB
- Sticky sessions: Up to 24 hours
- Why: Has dedicated Twitter proxy page, 99.2-99.5% success rate
- Website: nodemaven.com

### Proxidize (Hardware SIM-based)
- Hardware: $349-799 for modem kits + carrier data plan
- Cloud: $99/month for 8GB, or $1/GB
- Why: IPs from real SIM cards — never been in any proxy pool before, pristine reputation
- Has dedicated X scraper on GitHub: github.com/proxidize/x-scraper
- Website: proxidize.com

### AirProxy
- Pricing: ~87 EUR/proxy/month, unlimited bandwidth
- Type: 4G mobile only
- Why: Unlimited bandwidth per proxy, recommended on BlackHatWorld for Twitter
- Website: airproxy.io

---

## Category 2: ISP/Static Residential (Good Stability)

Datacenter IPs registered to real ISP blocks (Comcast, AT&T, etc.). Appear as home broadband users.

### Smartproxy / Decodo
- Pool: 100M+ residential IPs
- Pricing: ~$13/GB residential
- Why: Dedicated social media scraping API, static ISP option
- Website: decodo.com

### SOAX
- Pool: 191M IPs, 195 countries
- Pricing: ~$6/GB
- Why: ISP-level targeting (target specific ISPs like Comcast/AT&T), clean reputation
- Website: soax.com

### NetNut
- Pool: 85M+ IPs
- Pricing: Custom/enterprise (~$300/month)
- Why: Direct ISP partnerships (not P2P) = lower IP contamination risk
- Website: netnut.io

### IPRoyal
- Pricing: ~$7/GB residential, $2-4/IP/month for static ISP
- Why: Low cost, good for testing different regions
- Website: iproyal.com

---

## Category 3: Budget Rotating Residential (Acceptable, Higher Block Rate)

### Infatica - ~$3-5/GB, 20M+ IPs
### HydraProxy - Trustpilot 4.7 stars, competitive pricing
### NSTProxy - $0.40/GB (cheapest), 110M+ IPs — test before committing

---

## AVOID

- **922Proxy** - Shut down Jan 2026, identified as botnet
- **GeoSurf** - Acquired by BrightData (same pool)
- **Any datacenter proxy** (AWS, GCP, Azure, DO) - Blocked at ASN level

---

## Configuration Rules for twscrape

1. Use **sticky sessions** — twscrape needs same IP per account session
2. Set proxy **per-account** in twscrape, not globally
3. Match IP geo to account region (US IP for US accounts)
4. Minimum **15s delay** between requests per account
5. Never use datacenter IPs — blocked at ASN level regardless of rotation
6. Geographic consistency — mismatches trigger account review
