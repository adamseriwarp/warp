# GitHub Actions Setup Guide
## Carrier Performance Report Generator

This guide will help you set up the automated carrier report generation using GitHub Actions.

---

## 📋 Prerequisites

- GitHub repository with admin access
- Database credentials (MySQL)
- Resend API key (for email functionality)

---

## 🔧 Setup Instructions

### Step 1: Configure GitHub Secrets

GitHub Secrets keep your sensitive credentials secure. Here's how to add them:

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the following secrets one by one:

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `DB_HOST` | `datahub-mysql.wearewarp.link` | Database host |
| `DB_USER` | `datahub-read` | Database username |
| `DB_PASSWORD` | `warpdbhub2` | Database password |
| `DB_NAME` | `datahub` | Database name |
| `RESEND_API_KEY` | `re_HZz4UQ8x_5tkWo5pAFCboeMC1EAM7PG1H` | Resend API key for emails |

**How to add a secret:**
- Click "New repository secret"
- Enter the **Name** (e.g., `DB_HOST`)
- Enter the **Secret** (e.g., `datahub-mysql.wearewarp.link`)
- Click "Add secret"
- Repeat for all 5 secrets

---

### Step 2: Add More Carriers (Optional)

To add more carriers to the dropdown menu:

1. Open `.github/workflows/generate-carrier-report.yml`
2. Find the `carrier_name` section (around line 10)
3. Add more carriers to the `options` list:

```yaml
options:
  - 'ILLYRIAN TRANSPORT LLC'
  - 'CARRIER NAME 2'
  - 'CARRIER NAME 3'
  - 'ALL_CARRIERS'
```

---

### Step 3: Commit and Push

```bash
git add .github/workflows/generate-carrier-report.yml
git add query_otp_clean.py
git add GITHUB_ACTIONS_SETUP.md
git commit -m "Add GitHub Actions workflow for carrier reports"
git push origin main
```

---

## 🚀 How to Use

### Generate a Report

1. Go to your GitHub repository
2. Click the **Actions** tab
3. Click **"Generate Carrier Performance Report"** in the left sidebar
4. Click **"Run workflow"** button (top right)
5. Fill in the form:
   - **Carrier Name:** Select from dropdown
   - **Email recipient:** (Optional) Enter email address or leave blank
6. Click **"Run workflow"**
7. Wait ~30-60 seconds for completion

### Download the Report

1. Click on the workflow run (it will have a yellow dot while running, green when done)
2. Scroll down to **Artifacts** section
3. Click to download:
   - `carrier-report-[NAME]-[NUMBER].pdf` - The PDF report
   - `carrier-data-[NAME]-[NUMBER].csv` - Raw data (optional)

---

## 📧 Email Functionality

### Option 1: Send Email During Generation
- When running the workflow, enter an email address in the "Email recipient" field
- The PDF will be automatically emailed

### Option 2: Skip Email
- Leave the "Email recipient" field blank
- Download the PDF from Artifacts instead

---

## 🔍 Troubleshooting

### Workflow Fails with "Database Connection Error"
- Check that all database secrets are set correctly
- Verify the database is accessible from GitHub's servers

### No PDF in Artifacts
- Check the workflow logs for errors
- Ensure the carrier name exists in the database

### Email Not Sending
- Verify `RESEND_API_KEY` secret is set correctly
- Check that the email address is valid
- For production, use a verified domain in Resend

---

## 🎯 Advanced Features

### Schedule Automatic Reports

To generate reports automatically (e.g., every Monday at 9 AM):

1. Edit `.github/workflows/generate-carrier-report.yml`
2. Add this under `on:`:

```yaml
on:
  workflow_dispatch:
    # ... existing config ...
  
  schedule:
    - cron: '0 9 * * 1'  # Every Monday at 9 AM UTC
```

### Generate for All Carriers

Select `ALL_CARRIERS` from the dropdown to generate reports for all carriers in one run.

---

## 📊 Monitoring

- View all workflow runs in the **Actions** tab
- Each run shows:
  - Who triggered it
  - Which carrier was selected
  - Success/failure status
  - Execution time
  - Download links for artifacts

---

## 🔒 Security Notes

- Never commit secrets directly to the repository
- Always use GitHub Secrets for sensitive data
- Artifacts are retained for 30 days by default
- Only repository collaborators can trigger workflows

---

## 💡 Tips

- Bookmark the Actions page for quick access
- Download artifacts within 30 days (they auto-delete after)
- Check the workflow logs if something goes wrong
- You can re-run failed workflows with the "Re-run jobs" button

---

## 📞 Support

If you encounter issues:
1. Check the workflow logs in the Actions tab
2. Verify all secrets are configured correctly
3. Ensure the carrier name matches exactly what's in the database

