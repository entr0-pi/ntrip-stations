# API Key

The API key is required to log in to the RTK2GO Station Finder application.

## Your API Key

```
7l33761epAHB17jPbQyKOBElQ3IFiaznmK9CgADSfwzzFdVL7Yw83SrK3wToTuNE
```

## JWT Token

Once you enter the API key, you'll receive a JWT token that:
- Expires in **15 minutes**
- Is stored as an **httpOnly cookie** (secure, XSS-proof)
- Is automatically sent with all requests
- Must be refreshed after expiration by logging in again
