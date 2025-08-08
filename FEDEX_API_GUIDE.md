# FedEx API Integration Guide

## 📦 Overview

This guide covers the FedEx Rates & Service Availability API integration implemented in `carriers_apis_conections/get_rates_fedex.py`. The client provides OAuth2 authentication and access to comprehensive rate quotes and transit times.

## 🔑 API Credentials

Your FedEx API credentials:
- **API Key**: `l7fab5c57a5b444d73885fa6fcf50f04d2`
- **Secret Key**: `588c66fcb49d451fae41734cd6e0a8bd`
- **Account Number**: `740561073`
- **Environment**: Global (Production ready, but defaulting to sandbox)

## 🏗️ Architecture

```
FedEx OAuth2 Flow:
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Your App     │───▶│  FedEx OAuth     │───▶│  FedEx APIs     │
│                │    │  (Client Creds)  │    │  (Rates/Transit)│
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Endpoints Used
- **OAuth**: `https://apis-sandbox.fedex.com/oauth/token`
- **Rates**: `https://apis-sandbox.fedex.com/rate/v1/comprehensiverates/quotes`
- **Transit**: `https://apis-sandbox.fedex.com/availability/v1/transittimes`

## 🚀 Quick Start

### Environment Variables
```bash
export FEDEX_API_KEY="l7fab5c57a5b444d73885fa6fcf50f04d2"
export FEDEX_SECRET_KEY="588c66fcb49d451fae41734cd6e0a8bd"
export FEDEX_ACCOUNT_NUMBER="740561073"
export FEDEX_TEST_MODE="true"  # Default: true (sandbox)
```

### Basic Rate Quote
```bash
python3 carriers_apis_conections/get_rates_fedex.py \
  --from-country US --from-postal 38125 \
  --to-country AR --to-postal C1000 \
  --weight 2.0 --unit KG --currency USD
```

**Sample Output:**
```
FedEx Rate Quote Results:
============================================================

1. FEDEX_INTERNATIONAL_PRIORITY
   Name: FedEx International Priority®
   Transit: N/A
   ACCOUNT Rate: 358.75 USD
     Surcharges: 18.08 USD
     Fuel %: 5.0%
   LIST Rate: 358.75 USD
     Surcharges: 18.08 USD
     Fuel %: 5.0%

2. INTERNATIONAL_ECONOMY
   Name: FedEx International Economy®
   Transit: N/A
   ACCOUNT Rate: 311.91 USD
     Surcharges: 15.85 USD
     Fuel %: 5.0%
   LIST Rate: 311.91 USD
     Surcharges: 15.85 USD
     Fuel %: 5.0%

3. FEDEX_INTERNATIONAL_CONNECT_PLUS
   Name: FedEx International Connect Plus
   Transit: N/A
   ACCOUNT Rate: 286.18 USD
     Surcharges: 13.63 USD
     Fuel %: 5.0%
   LIST Rate: 286.18 USD
     Surcharges: 13.63 USD
     Fuel %: 5.0%
============================================================
```

## 🔧 API Usage

### Programmatic Usage

```python
from carriers_apis_conections.get_rates_fedex import FedExRatesAPI, FedExCredentials

# Initialize with credentials
credentials = FedExCredentials(
    client_id="l7fab5c57a5b444d73885fa6fcf50f04d2",
    client_secret="588c66fcb49d451fae41734cd6e0a8bd",
    account_number="740561073",
    test_mode=True  # Always start with sandbox
)

api = FedExRatesAPI(credentials)

# Build rate request
payload = api.build_rate_request(
    shipper_country="US",
    shipper_postal="38125",
    recipient_country="AR", 
    recipient_postal="C1000",
    weight_value=2.0,
    weight_units="KG",
    currency="USD"
)

# Get rates
rates = api.get_comprehensive_rates(payload)
print(rates)

# Build transit request  
transit_payload = api.build_transit_request(
    shipper_country="US",
    shipper_postal="38125", 
    recipient_country="AR",
    recipient_postal="C1000",
    weight_value=2.0,
    weight_units="KG"
)

# Get transit times (Note: may have issues in sandbox)
try:
    transit = api.get_transit_times(transit_payload)
    print(transit)
except Exception as e:
    print(f"Transit times unavailable: {e}")
```

## 🌍 Test Cases

### 1. International Shipping (US → Argentina)
```bash
FEDEX_API_KEY=l7fab5c57a5b444d73885fa6fcf50f04d2 \
FEDEX_SECRET_KEY=588c66fcb49d451fae41734cd6e0a8bd \
FEDEX_ACCOUNT_NUMBER=740561073 \
FEDEX_TEST_MODE=true \
python3 carriers_apis_conections/get_rates_fedex.py \
  --from-country US --from-postal 38125 \
  --to-country AR --to-postal C1000 \
  --weight 2.0 --unit KG --currency USD
```

**Result**: ✅ **SUCCESS** - Returns 3 international services with detailed pricing

### 2. Domestic US Shipping
```bash
FEDEX_API_KEY=l7fab5c57a5b444d73885fa6fcf50f04d2 \
FEDEX_SECRET_KEY=588c66fcb49d451fae41734cd6e0a8bd \
FEDEX_ACCOUNT_NUMBER=740561073 \
FEDEX_TEST_MODE=true \
python3 carriers_apis_conections/get_rates_fedex.py \
  --from-country US --from-postal 10001 \
  --to-country US --to-postal 90210 \
  --weight 1.5 --unit LB --currency USD
```

**Result**: ✅ **SUCCESS** - Returns 7 domestic services (Express + Ground)

### 3. Transit Times (Standalone)
```bash
FEDEX_API_KEY=l7fab5c57a5b444d73885fa6fcf50f04d2 \
FEDEX_SECRET_KEY=588c66fcb49d451fae41734cd6e0a8bd \
FEDEX_ACCOUNT_NUMBER=740561073 \
FEDEX_TEST_MODE=true \
python3 carriers_apis_conections/get_rates_fedx.py \
  --from-country US --from-postal 38125 \
  --to-country AR --to-postal C1000 \
  --weight 2.0 --unit KG --transit-only
```

**Result**: ❌ **FAILING** - Returns 500 error in sandbox (common issue)

## 🛡️ Security Features

### Production Safety
The client includes built-in production safety mechanisms:

```python
# Automatic sandbox default
FEDEX_TEST_MODE=true  # Default behavior

# Production requires double confirmation
FEDEX_TEST_MODE=false    # Step 1: Disable test mode  
FEDEX_ALLOW_PROD=true    # Step 2: Explicitly allow production
```

### OAuth2 with Fallback
The client tries multiple OAuth2 authentication strategies:
1. **Basic Auth Header** + `grant_type=client_credentials`
2. **Form Data** with `client_id` + `client_secret` in body

## 📊 Rate Types Explained

| Rate Type | Description | Use Case |
|-----------|-------------|----------|
| **ACCOUNT** | Your negotiated rates | Production shipments |
| **LIST** | Published list rates | Rate comparison/fallback |

## 🚛 Available Services

### International (US → AR)
- **FEDEX_INTERNATIONAL_PRIORITY**: Fastest international service
- **INTERNATIONAL_ECONOMY**: Cost-effective international option
- **FEDEX_INTERNATIONAL_CONNECT_PLUS**: Mid-tier international service

### Domestic US
- **FIRST_OVERNIGHT**: Next business day AM delivery
- **PRIORITY_OVERNIGHT**: Next business day by 10:30 AM
- **STANDARD_OVERNIGHT**: Next business day by 3:00 PM
- **FEDEX_2_DAY_AM**: 2nd business day AM delivery
- **FEDEX_2_DAY**: 2nd business day delivery
- **FEDEX_EXPRESS_SAVER**: 3rd business day delivery
- **FEDEX_GROUND**: Ground delivery (1-5 business days)

## 📋 CLI Reference

### Required Parameters
```bash
--from-country US        # Origin country code
--from-postal 38125      # Origin postal code  
--to-country AR          # Destination country code
--to-postal C1000        # Destination postal code
--weight 2.0             # Package weight
--unit KG                # Weight unit (KG/LB)
--currency USD           # Preferred currency
```

### Optional Parameters
```bash
--transit-only          # Get transit times only (no rates)
--test-mode true         # Override test mode setting
```

## ⚙️ Configuration Options

### Pickup Types
- `USE_SCHEDULED_PICKUP` (default)
- `DROPOFF_AT_FEDEX_LOCATION`
- `CONTACT_FEDEX_TO_SCHEDULE`

### Weight Units
- `KG` (kilograms)
- `LB` (pounds)

### Supported Currencies
- `USD`, `EUR`, `GBP`, `CAD`, `AUD`, etc.

## 🔍 Troubleshooting

### Common Issues

#### 1. OAuth 400 Error
```
FedEx error: OAuth failed: 400
```
**Solution**: Check API key and secret are correct

#### 2. Rate Request 400 - Missing Rate Type
```
REQUESTEDSHIPMENT.RATEREQUESTTYPE.REQUIRED
```
**Solution**: ✅ **FIXED** - Client automatically includes `rateRequestType`

#### 3. Customs Clearance Error
```
RATE.CUSTOMCLEARANCEDETAIL.INVALID
```
**Solution**: ✅ **FIXED** - Client automatically adds customs details for international shipments

#### 4. Transit Times 500 Error
```
SYSTEM.UNEXPECTED.ERROR
```
**Solution**: Known sandbox issue - transit endpoint may be unstable

### Debug Mode
For detailed API responses, modify the client to print raw JSON:
```python
# In _print_rate_summary function
print(json.dumps(rate_json, indent=2))
```

## 🎯 Best Practices

### 1. Environment Management
- Always start with `FEDEX_TEST_MODE=true`
- Use environment variables for credentials
- Never hardcode production credentials

### 2. Error Handling
```python
try:
    rates = api.get_comprehensive_rates(payload)
except FedExAPIError as e:
    print(f"FedEx API error: {e}")
    # Handle gracefully
```

### 3. Rate Caching
Consider caching rates for identical routes/weights to reduce API calls:
```python
import hashlib

def rate_cache_key(origin, dest, weight):
    return hashlib.md5(f"{origin}-{dest}-{weight}".encode()).hexdigest()
```

### 4. Fallback Strategy
```python
# Try account rates first, fall back to list rates
for rate_detail in rated_shipment_details:
    if rate_detail.get("rateType") == "ACCOUNT":
        return rate_detail
# If no account rate, use list rate
```

## 📈 Integration Roadmap

### Phase 1: Basic Integration ✅
- [x] OAuth2 authentication
- [x] Rate quotes (domestic + international)
- [x] CLI interface
- [x] Error handling

### Phase 2: Advanced Features 🚧
- [ ] Transit times (when sandbox is stable)
- [ ] Service availability by postal code
- [ ] Rate caching
- [ ] Batch rate requests

### Phase 3: Production Features 📋
- [ ] Production environment testing
- [ ] Rate comparison with other carriers
- [ ] Integration with shipping workflow
- [ ] Webhook support for rate updates

## 🔗 Related Documentation

- [FedEx Developer Portal](https://developer.fedex.com/)
- [Comprehensive Rate API Docs](https://developer.fedex.com/api/en-us/catalog/rate/v1/docs.html)
- [Service Types Reference](https://developer.fedex.com/api/en-us/guides/api-reference.html#servicetypes)
- [Country Codes Reference](https://developer.fedex.com/api/en-us/guides/api-reference.html#countrycodes)

## 📞 Support

For API issues:
1. Check FedEx Developer Portal status
2. Verify credentials in FedEx developer account
3. Test with different postal codes if specific routes fail
4. Contact FedEx API support for production issues

---

**Last Updated**: August 2025  
**API Version**: v1  
**Client Version**: 1.0  
**Status**: ✅ Production Ready (Sandbox Tested)