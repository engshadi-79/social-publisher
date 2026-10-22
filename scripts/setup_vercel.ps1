# يضبط الأسرار الناقصة لنشر اللوحة على Vercel. شغّله مرة واحدة من PowerShell:
#   powershell -ExecutionPolicy Bypass -File D:\ai\social-publisher\scripts\setup_vercel.ps1
# كل مفتاح تلصقه هنا يُرسل مباشرة إلى Vercel/GitHub ولا يُطبع ولا يُحفظ في ملف.
$ErrorActionPreference = "Stop"
$repo = "engshadi-79/social-publisher"
$site = "D:\ai\social-publisher\vercel-site"

function Read-Secret($prompt) {
  $s = Read-Host $prompt -AsSecureString
  $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}

Write-Host "`n1) مفتاح GitHub (للموافقة والتعديل من اللوحة)" -ForegroundColor Cyan
Write-Host "   سأفتح صفحة الإنشاء: Only select repositories -> social-publisher، الأذونات: Contents + Actions = Read and write"
Start-Process "https://github.com/settings/personal-access-tokens/new"
$pat = Read-Secret "الصق مفتاح GitHub هنا ثم Enter"
if ($pat) {
  Push-Location $site
  $pat | vercel env add GITHUB_PAT production --sensitive --force
  Pop-Location
  Write-Host "   تم حفظه في Vercel" -ForegroundColor Green
}

Write-Host "`n2) توكن Vercel (لتحديث اللوحة تلقائياً مع كل بناء)" -ForegroundColor Cyan
Start-Process "https://vercel.com/account/tokens"
$vt = Read-Secret "الصق توكن Vercel هنا ثم Enter"
if ($vt) {
  $vt | gh secret set VERCEL_TOKEN -R $repo
  Write-Host "   تم حفظه في GitHub" -ForegroundColor Green
}

Write-Host "`n3) نشر اللوحة وبناؤها" -ForegroundColor Cyan
Push-Location $site
vercel deploy --prod --yes
Pop-Location
gh workflow run dashboard -R $repo
Write-Host "`nانتهى. افتح https://social-dashboard-cyan-mu.vercel.app/ وسجّل الدخول." -ForegroundColor Green
