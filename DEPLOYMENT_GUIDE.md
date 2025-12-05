# Streamlit Cloud Deployment Guide

## Prerequisites
- GitHub account
- Streamlit Cloud account (free - sign up at https://share.streamlit.io)
- Your code pushed to a GitHub repository

## Step-by-Step Deployment

### 1. Push Your Code to GitHub

First, make sure all your files are committed and pushed to GitHub:

```bash
# Check status
git status

# Add all files
git add app.py report_generator.py requirements.txt .streamlit/config.toml STREAMLIT_GUIDE.md

# Commit
git commit -m "Add Streamlit carrier performance report app"

# Push to GitHub
git push origin main
```

**IMPORTANT**: Do NOT commit `.streamlit/secrets.toml` - it's already in `.gitignore`

### 2. Sign Up for Streamlit Cloud

1. Go to https://share.streamlit.io
2. Click "Sign up" or "Continue with GitHub"
3. Authorize Streamlit to access your GitHub account

### 3. Deploy Your App

1. Click "New app" button
2. Fill in the form:
   - **Repository**: Select `adamseriwarp/warp` (or your repo name)
   - **Branch**: `main`
   - **Main file path**: `app.py`
   - **App URL**: Choose a custom URL (e.g., `warp-carrier-reports`)

3. Click "Advanced settings" (IMPORTANT!)

4. In the "Secrets" section, paste this TOML content:
   ```toml
   [database]
   host = "datahub-mysql.wearewarp.link"
   user = "datahub-read"
   password = "warpdbhub2"
   database = "datahub"
   ```

5. Click "Deploy!"

### 4. Wait for Deployment

- Streamlit will install dependencies from `requirements.txt`
- This takes 2-5 minutes
- You'll see a build log showing progress
- Once complete, your app will be live!

### 5. Access Your App

Your app will be available at:
```
https://YOUR-APP-NAME.streamlit.app
```

For example:
```
https://warp-carrier-reports.streamlit.app
```

## Managing Your Deployed App

### Update the App
Just push changes to GitHub:
```bash
git add .
git commit -m "Update report features"
git push origin main
```

Streamlit Cloud will automatically redeploy within 1-2 minutes.

### View Logs
1. Go to https://share.streamlit.io
2. Click on your app
3. Click "Manage app" → "Logs"

### Reboot the App
If the app crashes or needs a restart:
1. Go to https://share.streamlit.io
2. Click on your app
3. Click "Manage app" → "Reboot app"

### Update Secrets
1. Go to https://share.streamlit.io
2. Click on your app
3. Click "Settings" → "Secrets"
4. Edit the TOML content
5. Click "Save"

### Delete the App
1. Go to https://share.streamlit.io
2. Click on your app
3. Click "Settings" → "Delete app"

## Adding Authentication (Optional)

### Option 1: Simple Password Protection

Add this to the top of `app.py`:

```python
import streamlit as st

def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct
        return True

if not check_password():
    st.stop()

# Rest of your app code...
```

Then add to your secrets in Streamlit Cloud:
```toml
password = "your-secure-password"
```

### Option 2: Email-Based Authentication

Use `streamlit-authenticator` package:
1. Add to `requirements.txt`: `streamlit-authenticator`
2. Follow docs: https://github.com/mkhorasani/Streamlit-Authenticator

## Troubleshooting

### App won't start
- Check the logs in Streamlit Cloud
- Verify all dependencies are in `requirements.txt`
- Make sure `app.py` is in the root directory

### Database connection error
- Check that secrets are configured correctly in Streamlit Cloud
- Verify database is accessible from external IPs
- Check firewall rules

### App is slow
- Free tier has limited resources (1 GB RAM, 1 CPU)
- Consider upgrading to paid tier ($20/month) for better performance
- Optimize caching with `@st.cache_data` and `@st.cache_resource`

### App crashes with large PDFs
- Free tier has memory limits
- Try reducing `rows_per_page` in detail tables
- Consider upgrading to paid tier

## Sharing with Your Team

Once deployed, share the URL with your team:
```
https://your-app-name.streamlit.app
```

They can:
- ✅ Access from any device (desktop, tablet, mobile)
- ✅ No installation required
- ✅ Always get the latest version
- ✅ Generate reports on-demand

## Cost

**Free Tier** (Streamlit Community Cloud):
- ✅ 1 GB RAM
- ✅ 1 CPU core
- ✅ Unlimited apps
- ✅ Free forever
- ✅ Perfect for internal tools with <100 users

**Paid Tier** ($20/month per app):
- 🚀 4 GB RAM
- 🚀 2 CPU cores
- 🚀 Faster performance
- 🚀 Priority support

## Next Steps

1. ✅ Push code to GitHub
2. ✅ Deploy to Streamlit Cloud
3. ✅ Add secrets
4. ✅ Test the deployed app
5. ✅ Share URL with team
6. ⭐ (Optional) Add authentication
7. ⭐ (Optional) Customize branding

## Support

- Streamlit Docs: https://docs.streamlit.io
- Streamlit Forum: https://discuss.streamlit.io
- Streamlit Cloud Docs: https://docs.streamlit.io/streamlit-community-cloud

