# Hosting Troubleshooting Guide - OAuth & SSL Issues

This document addresses common issues when hosting Workforce Agent with:
- **Frontend**: Vercel (`https://dinoagent.vercel.app`)
- **Backend**: AWS EC2 (`https://api.dinoagent.run.place`)
- **Database**: Supabase

---

## Summary of Issues

| Issue | Symptoms | Root Cause |
|-------|----------|------------|
| **SSL Error on WiFi** | "SSL error", "unsafe site" warnings, won't load | SSL certificate problems OR network-level SSL inspection |
| **Works on Mobile Data (same Mac)** | Everything works perfectly | Confirms WiFi network is the problem for issue #1 |
| **OAuth Loop on Other Devices** | Sign in → OAuth → redirects back → Sign in again (infinite loop) | **Third-party cookie blocking** - frontend and backend on different domains |

---

## Issue #1: SSL Errors on WiFi

### Diagnosis

The SSL error only happens on WiFi but not mobile data. This indicates:

1. **Your WiFi network** (home router, corporate network, or ISP) is interfering with SSL
2. **Possible causes**:
   - Corporate/school firewall doing SSL inspection
   - Router with "security" features intercepting HTTPS
   - DNS-level blocking or filtering
   - Cached bad SSL certificate

### How to Verify Your Backend SSL Certificate

Run these commands from your Mac (on mobile data or different network):

```bash
# Check if the certificate is valid
curl -vI https://api.dinoagent.run.place/health

# Check certificate details
echo | openssl s_client -servername api.dinoagent.run.place -connect api.dinoagent.run.place:443 2>/dev/null | openssl x509 -noout -dates -issuer

# Test from a different DNS
curl --resolve api.dinoagent.run.place:443:$(dig +short api.dinoagent.run.place @8.8.8.8) -I https://api.dinoagent.run.place/health
```

### Possible SSL Fixes

#### A. Renew/Reinstall Let's Encrypt Certificate on EC2

SSH into your EC2 instance:

```bash
# Check current certificate status
sudo certbot certificates

# Force renewal
sudo certbot renew --force-renewal

# Restart nginx
sudo systemctl restart nginx
```

#### B. Verify Nginx SSL Configuration

```bash
sudo cat /etc/nginx/conf.d/workforce-backend.conf
```

Should include (after Certbot ran):
```nginx
server {
    listen 443 ssl;
    server_name api.dinoagent.run.place;
    
    ssl_certificate /etc/letsencrypt/live/api.dinoagent.run.place/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.dinoagent.run.place/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    
    # ... rest of config
}
```

#### C. If WiFi is Corporate/School Network

Corporate networks often use **SSL interception** (man-in-the-middle) for security monitoring. You cannot fix this - users on such networks will always have issues unless:
- IT whitelists your domain
- Users use a VPN
- Users use mobile data

**This is a network policy issue, not your code.**

---

## Issue #2: OAuth Login Loop on Other Devices (THE MAIN ISSUE)

### Root Cause: Third-Party Cookie Blocking

**This is your primary problem.** Here's why it happens:

```
Frontend Domain:  https://dinoagent.vercel.app
Backend Domain:   https://api.dinoagent.run.place
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                  COMPLETELY DIFFERENT DOMAINS
```

When the OAuth callback completes:
1. Backend sets a session cookie on `api.dinoagent.run.place`
2. Frontend at `dinoagent.vercel.app` makes a request to `/auth/me`
3. Browser treats the cookie as **third-party** (different domain)
4. **Modern browsers block third-party cookies by default**
5. Cookie is not sent → User appears not logged in → Login loop

### Why It Works on YOUR Mac

On your development Mac, you likely have:
- Previously logged in during development (cookies cached)
- Browser settings that allow third-party cookies
- Safari ITP exceptions for localhost testing

### Browsers Blocking Third-Party Cookies (as of 2024-2025)

| Browser | Third-Party Cookie Status |
|---------|---------------------------|
| Safari | **Blocked by default** (ITP since 2017) |
| Firefox | **Blocked by default** (ETP since 2019) |
| Chrome | **Phasing out** (fully blocked by Q3 2024) |
| Edge | Following Chrome's timeline |
| Brave | **Blocked by default** |

---

## Solutions for OAuth Loop

### ✅ **RECOMMENDED: Solution 1 - Same Root Domain**

The most reliable fix is to use the **same root domain** for frontend and backend:

```
Frontend:  https://app.dinoagent.com     (or dinoagent.com)
Backend:   https://api.dinoagent.com
                   ^^^^^^^^^^^^
                   SAME ROOT DOMAIN
```

With same root domain, cookies can be shared using:
```python
response.set_cookie(
    key="wf_session",
    value=session_id,
    domain=".dinoagent.com",  # Leading dot = all subdomains
    secure=True,
    httponly=True,
    samesite="lax",  # Can use "lax" instead of "none"
)
```

**Steps to implement:**

1. **Get a domain** (e.g., `dinoagent.com` from Namecheap, Google Domains, etc.)

2. **Point subdomains**:
   - `app.dinoagent.com` → Vercel (CNAME to `cname.vercel-dns.com`)
   - `api.dinoagent.com` → EC2 Elastic IP (A record)

3. **Update Vercel**:
   - Add custom domain `app.dinoagent.com`
   - Set `VITE_API_BASE_URL=https://api.dinoagent.com`

4. **Update EC2 `.env`**:
   ```env
   FRONTEND_BASE_URL=https://app.dinoagent.com
   GOOGLE_OAUTH_REDIRECT_BASE=https://api.dinoagent.com
   ```

5. **Update Google OAuth Console**:
   - Authorized redirect URI: `https://api.dinoagent.com/auth/google/callback`

6. **Update backend cookie code** (see code changes below)

7. **Renew SSL certificate**:
   ```bash
   sudo certbot --nginx -d api.dinoagent.com
   ```

---

### Solution 2 - Vercel API Proxy (No Custom Domain Needed)

Proxy all `/api` requests through Vercel to your backend. This makes everything same-origin.

**Frontend `vercel.json`:**

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://api.dinoagent.run.place/:path*"
    }
  ]
}
```

**Pros:**
- No custom domain needed
- Everything is same-origin
- Cookies work naturally

**Cons:**
- Added latency (request goes Vercel → EC2)
- WebSocket proxying is more complex
- Vercel has request limits on free tier

---

### Solution 3 - Token-Based Auth (localStorage)

Instead of cookies, use JWT tokens stored in localStorage.

**Backend changes:**
- Return token in response body instead of cookie
- Accept `Authorization: Bearer <token>` header

**Frontend changes:**
- Store token in localStorage
- Send token in Authorization header

**Pros:**
- Works regardless of domains
- No cookie issues

**Cons:**
- Less secure (XSS can steal tokens)
- More code changes required
- Need to handle token refresh

---

## Recommended Code Changes for Solution 1 (Same Domain)

### Backend: `backend/core/config.py`

Add a new config for cookie domain:

```python
# Cookie domain for cross-subdomain sharing
# Set to ".yourdomain.com" in production for subdomain cookie sharing
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", "")
```

### Backend: `backend/api/main.py`

Update `_cookie_settings()`:

```python
def _cookie_settings() -> Dict[str, Any]:
    """Get cookie settings based on environment."""
    frontend_url = Config.FRONTEND_BASE_URL or ""
    
    is_local = (
        frontend_url.startswith("http://localhost")
        or frontend_url.startswith("http://127.0.0.1")
        or not frontend_url  # Empty = local dev
    )

    if is_local:
        return {
            "path": "/",
            "httponly": True,
            "secure": False,
            "samesite": "lax",
        }

    # Production settings
    settings = {
        "path": "/",
        "httponly": True,
        "secure": True,
        "samesite": "lax",  # Can use "lax" with same root domain
    }
    
    # If COOKIE_DOMAIN is set, use it for cross-subdomain sharing
    cookie_domain = Config.COOKIE_DOMAIN
    if cookie_domain:
        settings["domain"] = cookie_domain
    
    return settings
```

### Backend `.env` for Production

```env
# Use your actual domain
FRONTEND_BASE_URL=https://app.dinoagent.com
GOOGLE_OAUTH_REDIRECT_BASE=https://api.dinoagent.com
COOKIE_DOMAIN=.dinoagent.com
CORS_ALLOWED_ORIGINS=https://app.dinoagent.com,https://dinoagent.com
```

---

## Google OAuth Console Configuration

Make sure your Google Cloud Console OAuth settings match:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services → Credentials**
3. Click on your OAuth 2.0 Client ID
4. Set:

**Authorized JavaScript origins:**
```
https://app.dinoagent.com
https://dinoagent.com
https://dinoagent.vercel.app  (keep for now as fallback)
```

**Authorized redirect URIs:**
```
https://api.dinoagent.com/auth/google/callback
https://api.dinoagent.run.place/auth/google/callback  (keep as fallback)
```

---

## Quick Verification Checklist

After making changes, verify:

### 1. SSL Certificate Valid
```bash
curl -I https://api.dinoagent.com/health
# Should return HTTP 200, no SSL errors
```

### 2. CORS Configured
```bash
curl -I -X OPTIONS https://api.dinoagent.com/api/chat/connectors/status \
  -H "Origin: https://app.dinoagent.com" \
  -H "Access-Control-Request-Method: GET"
# Should return Access-Control-Allow-Origin: https://app.dinoagent.com
```

### 3. Cookie Domain Correct
Open browser DevTools → Application → Cookies after logging in:
- Cookie name: `wf_session`
- Domain: `.dinoagent.com` (with leading dot)
- Secure: ✓
- HttpOnly: ✓
- SameSite: Lax

### 4. OAuth Redirect Correct
After clicking Sign In, check the URL bar:
- Should redirect to Google
- After approval, should redirect to `https://app.dinoagent.com/?_session_token=...`
- Should then show logged in state

---

## Debugging Tips

### View Backend Logs
```bash
sudo journalctl -u workforce-backend -f
```

Look for:
```
OAuth callback successful - User: user@email.com, SessionID: xxx
Setting session cookie - SessionID: xxx, Settings: {...}
```

### Browser DevTools
1. **Network tab**: Look for `/auth/me` request - does it include cookies?
2. **Console tab**: Look for CORS errors
3. **Application tab**: Check what cookies are set and their domain

### Test Session Exchange
```bash
# If _session_token workaround is being used
curl -X POST https://api.dinoagent.com/auth/session-exchange \
  -H "Content-Type: application/json" \
  -d '{"token": "your-session-token"}' \
  -v
# Check Set-Cookie header in response
```

---

## Summary: What You Need To Do

### Immediate Fix (Recommended)

1. **Register a domain** (e.g., `dinoagent.com`) - ~$10-15/year

2. **Set up DNS**:
   - `app.dinoagent.com` → CNAME → `cname.vercel-dns.com`
   - `api.dinoagent.com` → A → Your EC2 Elastic IP

3. **Update Vercel**:
   - Add custom domain
   - Update `VITE_API_BASE_URL=https://api.dinoagent.com`

4. **Update EC2**:
   ```bash
   # Update .env
   nano ~/Workforce-agent/.env
   # Set:
   # FRONTEND_BASE_URL=https://app.dinoagent.com
   # GOOGLE_OAUTH_REDIRECT_BASE=https://api.dinoagent.com
   # COOKIE_DOMAIN=.dinoagent.com
   
   # Get new SSL cert
   sudo certbot --nginx -d api.dinoagent.com
   
   # Restart backend
   sudo systemctl restart workforce-backend
   ```

5. **Update Google OAuth Console**:
   - Add new redirect URI

6. **Test on incognito/different device**

### Cost
- Domain: ~$10-15/year
- Everything else: Free (Vercel hobby, EC2 free tier, Supabase free)

---

## Why The Current Setup Fails

```
Current Setup:
┌─────────────────────────────────────────────────────────────┐
│  dinoagent.vercel.app  ←--cookies blocked--→  api.dinoagent.run.place  │
│      (Vercel)                                    (EC2)                   │
│                                                                          │
│  Different domains = Third-party cookies = BLOCKED                       │
└─────────────────────────────────────────────────────────────┘

Fixed Setup:
┌─────────────────────────────────────────────────────────────┐
│  app.dinoagent.com  ←--cookies shared--→  api.dinoagent.com  │
│      (Vercel)                               (EC2)             │
│                                                               │
│  Same root domain = First-party cookies = WORKS              │
└─────────────────────────────────────────────────────────────┘
```

---

## FAQ

**Q: Why did it work on my Mac with mobile data?**
A: Your browser likely had cached cookies from previous development, or you have third-party cookies enabled in settings.

**Q: Can I just enable third-party cookies?**
A: You can't ask all your users to change their browser settings. Browsers are moving to block third-party cookies entirely.

**Q: Is the Vercel proxy option good?**
A: It works but adds latency and has limitations with WebSockets. Same-domain is cleaner.

**Q: Do I need a paid domain?**
A: Yes, for proper production. ~$10-15/year is minimal for a working auth system.

**Q: What about free subdomains like Freenom?**
A: They're unreliable and often get blocked. Not recommended for production.
