# QR Code Contact Generator (Static Site)

A fully static web application that generates QR codes for contacts. Everything runs in your browser - no server, no database, no data storage.

## ✨ Features

- **100% Client-Side**: All processing happens in your browser
- **No Data Storage**: Nothing is saved - completely private
- **Instant QR Generation**: Create scannable QR codes in seconds
- **Two QR Modes**:
  - **vCard QR**: Direct contact data (best for iOS)
  - **Google Contacts Link**: One-tap save for Android
- **Mobile Optimized**: Works perfectly on iOS and Android
- **Premium Design**: Dark mode with glassmorphism effects
- **Offline Ready**: Works without internet after initial load

## 🚀 Deploy to Netlify

### Option 1: Drag & Drop (Easiest)

1. Go to [Netlify Drop](https://app.netlify.com/drop)
2. Drag the entire project folder onto the page
3. Done! Your site is live instantly

### Option 2: GitHub + Netlify (Recommended)

1. **Push to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin YOUR_GITHUB_REPO_URL
   git push -u origin main
   ```

2. **Deploy on Netlify**:
   - Go to [Netlify](https://app.netlify.com)
   - Click "Add new site" → "Import an existing project"
   - Connect your GitHub repository
   - Build settings:
     - **Build command**: (leave empty)
     - **Publish directory**: `.` (root)
   - Click "Deploy site"

3. **Your site is live!** 🎉

### Option 3: Netlify CLI

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Login
netlify login

# Deploy
netlify deploy --prod
```

## 💻 Local Testing

Simply open `index.html` in your browser:

```bash
# Option 1: Double-click index.html

# Option 2: Use a local server (recommended)
# Python 3
python -m http.server 8000

# Node.js
npx http-server

# Then open: http://localhost:8000
```

## 📱 How to Use

1. **Fill out the contact form** with name, phone, email, etc.
2. **Click "Generate QR Code"**
3. **Choose QR mode**:
   - **vCard QR**: Best for iOS - scan and add directly
   - **Share Link**: Opens Google Contacts for easy save
4. **Download options**:
   - Download QR code as PNG image
   - Download vCard file (.vcf)
   - Share directly on mobile (Web Share API)

## 📱 Mobile Testing

### iOS (iPhone/iPad)
1. Generate QR code on computer
2. Open Camera app
3. Point at **vCard QR** code
4. Tap notification → "Add Contact" opens instantly ✅

### Android
1. Generate QR code
2. Use Google Lens or Camera
3. For **Share Link QR**: Opens Google Contacts → One-tap save ✅
4. For **vCard QR**: Download → Open file → Save to contacts

## 🛠️ Technical Details

### Architecture
- **Pure Static Site**: HTML + CSS + JavaScript
- **No Backend**: Everything runs client-side
- **No Database**: No data persistence
- **No Build Process**: Deploy as-is

### Libraries Used
- [qrcode.js](https://github.com/soldair/node-qrcode) - QR code generation (CDN)
- Google Fonts (Outfit) - Typography

### Browser Compatibility
- ✅ Chrome/Edge (Desktop & Mobile)
- ✅ Safari (Desktop & Mobile)
- ✅ Firefox (Desktop)
- ✅ Samsung Internet (Mobile)

### Features by Browser
| Feature | Chrome | Safari | Firefox |
|---------|--------|--------|---------|
| QR Generation | ✅ | ✅ | ✅ |
| vCard Download | ✅ | ✅ | ✅ |
| Web Share API | ✅ Mobile | ✅ iOS | ❌ |

## 📂 Project Structure

```
QR Code Generator/
├── index.html          # Main HTML file
├── app.js             # JavaScript logic
├── style.css          # Styles
├── netlify.toml       # Netlify config
└── README.md          # This file
```

## 🔒 Privacy & Security

- **No data collection**: Nothing is sent to any server
- **No tracking**: No analytics or cookies
- **No storage**: Contacts are never saved
- **Client-side only**: All processing in your browser
- **HTTPS**: Automatically provided by Netlify

## 🎨 Customization

### Change Colors
Edit `style.css` and modify CSS variables:
```css
:root {
    --primary-color: #3b82f6;  /* Change to your brand color */
    --bg-color: #0f172a;       /* Background color */
}
```

### Add Logo
Add an `<img>` tag in `index.html` before the `<h1>` tag.

## 🐛 Troubleshooting

### QR Code Not Generating
- Check browser console for errors
- Ensure JavaScript is enabled
- Try a different browser

### QR Code Not Scanning
- Increase screen brightness
- Ensure good lighting
- Try the other QR mode (vCard ↔ Share Link)

### Mobile Share Not Working
- Web Share API only works on HTTPS
- Not supported on Firefox mobile
- Fallback: Use download buttons

## 📄 License

MIT License - Free to use and modify

## 🙏 Credits

Built with ❤️ using vanilla JavaScript and qrcode.js

---

**Need help?** Open an issue on GitHub or contact support.
