# Free API Setup Guide

This scraper tool now uses **100% FREE APIs** - no credit card required!

## Available FREE APIs

### 1. OpenStreetMap Overpass API (New!)
- **Cost**: FREE (no API key required)
- **Rate Limits**: 1 request per second (recommended)
- **Use Case**: Query steakhouses and other POIs from OpenStreetMap
- **Environment Variable**: None required!
- **Documentation**: See `OSM_API_SETUP.md`

**Features:**
- Search steakhouses by location
- Get comprehensive OSM data (address, coordinates, amenities, etc.)
- Optional data enhancement with web scraping
- AI-powered steak cut type extraction
- Multiple location formats supported

### 2. Google Gemini AI (Recommended)
- **Cost**: FREE (no credit card required)
- **Rate Limits**: Generous free tier
- **Use Case**: AI-powered data extraction and filtering
- **Get API Key**: https://makersuite.google.com/app/apikey
- **Environment Variable**: `GEMINI_API_KEY`

**Features:**
- Automatic fallback to smart extraction if API key not set
- Multiple free model options (gemini-1.5-flash, gemini-pro, etc.)
- Graceful handling of rate limits

### 3. Yelp Fusion API
- **Cost**: FREE (no credit card required)
- **Rate Limits**: 5,000 API calls per day
- **Use Case**: Restaurant/business search and data
- **Get API Key**: https://www.yelp.com/developers/v3/manage_app
- **Environment Variable**: `YELP_API_KEY`

**Features:**
- Daily call tracking
- Automatic rate limit warnings
- Usage statistics endpoint

### 4. Smart Extraction (No API Required)
- **Cost**: FREE (always available)
- **Use Case**: Pattern-based data extraction without AI
- **Features**: Automatically used when AI APIs are not available

## Setup Instructions

### 1. Set Up Google Gemini (Optional but Recommended)

1. Visit https://makersuite.google.com/app/apikey
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy your API key
5. Set it as an environment variable:
   ```bash
   export GEMINI_API_KEY="your-api-key-here"
   ```
   Or add to `.env` file:
   ```
   GEMINI_API_KEY=your-api-key-here
   ```

### 2. Set Up Yelp API (Optional)

1. Visit https://www.yelp.com/developers/v3/manage_app
2. Sign in or create a Yelp account
3. Create a new app
4. Copy your API key
5. Set it as an environment variable:
   ```bash
   export YELP_API_KEY="your-api-key-here"
   ```
   Or add to `.env` file:
   ```
   YELP_API_KEY=your-api-key-here
   ```

### 3. Verify Setup

Check API status:
```bash
# Check Gemini API
curl http://localhost:8000/api/debug

# Check Yelp API
curl http://localhost:8000/api/yelp/status
```

## Rate Limits & Best Practices

### Google Gemini
- Free tier has generous limits
- Automatic fallback to smart extraction if limits are reached
- No action needed - handled automatically

### Yelp API
- **FREE Tier**: 5,000 calls per day
- Resets at midnight
- Usage tracking built-in
- Warnings when approaching limit

**Monitor Usage:**
```bash
curl http://localhost:8000/api/yelp/status
```

Response includes:
- `calls_used`: Number of calls made today
- `calls_remaining`: Calls left for today
- `daily_limit`: 5000 (FREE tier)

## What Changed

### Removed
- ❌ OpenAI API (required paid subscription)
- ❌ Any paid API dependencies

### Updated
- ✅ Google Gemini prioritized (FREE tier)
- ✅ Better error handling for rate limits
- ✅ Automatic fallback to smart extraction
- ✅ Rate limit tracking for Yelp API
- ✅ Improved documentation

## Fallback Behavior

The system gracefully handles missing API keys:

1. **If Gemini API key not set:**
   - Uses smart extraction (pattern-based)
   - Still works, just without AI assistance
   - Logs helpful message with setup link

2. **If Yelp API key not set:**
   - Yelp-specific endpoints won't work
   - Regular scraping still works
   - Can scrape Yelp pages directly (no API needed)

3. **If rate limits exceeded:**
   - Gemini: Falls back to smart extraction
   - Yelp: Returns clear error with usage stats

## Cost Summary

| Service | Cost | Credit Card Required |
|---------|------|---------------------|
| OpenStreetMap Overpass | FREE | ❌ No |
| Google Gemini | FREE | ❌ No |
| Yelp API | FREE | ❌ No |
| Smart Extraction | FREE | ❌ No |
| **Total** | **$0.00** | **❌ No** |

## Troubleshooting

### "Gemini API not working"
- Check API key is set correctly
- Verify key is valid at https://makersuite.google.com/app/apikey
- System will automatically use smart extraction as fallback

### "Yelp API rate limit exceeded"
- You've used all 5,000 free calls for today
- Wait until midnight (resets daily)
- Check usage: `curl http://localhost:8000/api/yelp/status`
- Consider batching requests or upgrading plan

### "No API keys set"
- That's okay! Smart extraction will be used
- For better results, add Gemini API key (free)
- See setup instructions above

## Support

For issues or questions:
1. Check API status endpoints
2. Review logs for detailed error messages
3. Verify environment variables are set correctly
4. Ensure you're using the FREE tier (no credit card needed)

