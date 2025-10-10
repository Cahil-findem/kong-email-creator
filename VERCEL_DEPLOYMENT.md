# Vercel Deployment Guide

## Setup Instructions

### 1. Environment Variables

You **MUST** set these environment variables in your Vercel dashboard:

Go to: Project Settings → Environment Variables

Add the following:

```
OPENAI_API_KEY=sk-your-openai-api-key-here
SUPABASE_URL=your-supabase-project-url
SUPABASE_KEY=your-supabase-anon-key
```

### 2. Deploy

The app is configured to deploy automatically from your GitHub repository.

Push your changes:
```bash
git add .
git commit -m "Fix environment variable loading for Vercel"
git push origin main
```

Vercel will automatically redeploy.

### 3. Verify Deployment

Visit your Vercel URL and check:
- Homepage loads: `https://your-app.vercel.app/`
- Health check works: `https://your-app.vercel.app/api/health`

### Common Issues

#### "OpenAI API key not set"
- Make sure you added `OPENAI_API_KEY` in Vercel dashboard
- Redeploy after adding environment variables

#### "Supabase connection failed"
- Check `SUPABASE_URL` and `SUPABASE_KEY` are correct
- Ensure your Supabase project is active

#### "Module not found"
- All dependencies in `requirements.txt` should install automatically
- Check Vercel build logs for errors

### Build Configuration

The `vercel.json` file is already configured:
- Python runtime with Flask
- Routes all requests to `app.py`
- Serverless function deployment

No additional configuration needed!
