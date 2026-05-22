using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

namespace SimpleAINovelAppLauncher
{
    internal static class Program
    {
        [STAThread]
        private static int Main()
        {
            LauncherSplash splash = null;
            try
            {
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                splash = new LauncherSplash(LauncherConfig.AppName);
                splash.Show();
                splash.SetStage("正在启动 " + LauncherConfig.AppName, "准备运行环境");
                Application.DoEvents();

                string exeDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                if (string.IsNullOrEmpty(exeDir))
                {
                    exeDir = Environment.CurrentDirectory;
                }

                string runtimeBase = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    LauncherConfig.AppName
                );

                string dataDir = Path.Combine(exeDir, "data");
                string[] legacyDataDirs = new string[]
                {
                    Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                        LauncherConfig.AppName, "data"
                    ),
                    Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                        "SimpleAINovelApp", "data"
                    )
                };

                string legacyDataEnv = string.Join(Path.PathSeparator.ToString(), legacyDataDirs);

                splash.SetStage("正在检查运行时", "首次启动可能需要解压文件");
                string installDir = EnsureInstallDir(Path.Combine(runtimeBase, "runtime"), LauncherConfig.Version);
                Directory.CreateDirectory(dataDir);

                string stampPath = Path.Combine(installDir, ".extracted");
                string pythonw = Path.Combine(installDir, "python", "pythonw.exe");
                string mainScript = Path.Combine(installDir, "app", "main.py");
                string expectedStamp = BuildPayloadStamp();
                if (NeedsExtract(stampPath, expectedStamp, pythonw, mainScript))
                {
                    splash.SetStage("正在准备运行时", "解压内置组件，请稍候");
                    DeleteDir(installDir);
                    Directory.CreateDirectory(installDir);
                    ExtractPayload(installDir, splash);
                    File.WriteAllText(stampPath, expectedStamp);
                }

                if (Environment.GetEnvironmentVariable("SIMPLE_AI_NOVEL_LAUNCHER_EXTRACT_ONLY") == "1")
                {
                    return 0;
                }

                if (!File.Exists(pythonw) || !File.Exists(mainScript))
                {
                    throw new FileNotFoundException(
                        "Runtime files could not be extracted.\n" +
                        "pythonw.exe: " + File.Exists(pythonw) + "\n" +
                        "main.py: " + File.Exists(mainScript) + "\n" +
                        "Install dir: " + installDir
                    );
                }

                ProcessStartInfo startInfo = new ProcessStartInfo();
                startInfo.FileName = pythonw;
                startInfo.Arguments = Quote(mainScript);
                startInfo.WorkingDirectory = Path.Combine(installDir, "app");
                startInfo.UseShellExecute = false;
                startInfo.EnvironmentVariables["SIMPLE_AI_NOVEL_DATA_DIR"] = dataDir;
                startInfo.EnvironmentVariables["SIMPLE_AI_NOVEL_LEGACY_DATA_DIRS"] = legacyDataEnv;
                startInfo.EnvironmentVariables["PYTHONHOME"] = Path.Combine(installDir, "python");
                startInfo.EnvironmentVariables["PYTHONPATH"] = "";
                startInfo.EnvironmentVariables["SIMPLE_AI_NOVEL_NATIVE_SPLASH"] = "1";
                splash.SetStage("正在加载主界面", "灵枢工作台正在后台启动");
                Process child = Process.Start(startInfo);
                WaitForChildWindow(child, splash);
                return 0;
            }
            catch (Exception exc)
            {
                try { Console.Error.WriteLine(exc.ToString()); } catch { }
                MessageBox.Show(
                    exc.Message,
                    LauncherConfig.AppName + " startup failed",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return 1;
            }
            finally
            {
                if (splash != null)
                {
                    splash.CloseSplash();
                }
            }
        }

        private static void WaitForChildWindow(Process child, LauncherSplash splash)
        {
            if (child == null)
            {
                return;
            }
            Stopwatch stopwatch = Stopwatch.StartNew();
            while (!child.HasExited && stopwatch.Elapsed.TotalSeconds < 45)
            {
                splash.Pump();
                child.Refresh();
                if (child.MainWindowHandle != IntPtr.Zero)
                {
                    splash.SetStage("启动完成", "正在打开工作台");
                    DateTime until = DateTime.Now.AddMilliseconds(240);
                    while (DateTime.Now < until)
                    {
                        splash.Pump();
                        Thread.Sleep(15);
                    }
                    return;
                }
                Thread.Sleep(35);
            }
        }

        private static string EnsureInstallDir(string parentDir, string baseName)
        {
            Directory.CreateDirectory(parentDir);
            string dir = Path.Combine(parentDir, baseName);
            try
            {
                Directory.CreateDirectory(dir);
                if (Directory.Exists(dir))
                {
                    return dir;
                }
            }
            catch { }

            dir = Path.Combine(parentDir, baseName + "_" + Guid.NewGuid().ToString("N").Substring(0, 8));
            Directory.CreateDirectory(dir);
            return dir;
        }

        private static string BuildPayloadStamp()
        {
            string exePath = Assembly.GetExecutingAssembly().Location;
            FileInfo fileInfo = new FileInfo(exePath);
            return LauncherConfig.Version + "|" + fileInfo.Length + "|" + fileInfo.LastWriteTimeUtc.Ticks;
        }

        private static bool NeedsExtract(string stampPath, string expectedStamp, string pythonw, string mainScript)
        {
            if (!File.Exists(pythonw) || !File.Exists(mainScript))
            {
                return true;
            }
            try
            {
                return !File.Exists(stampPath) || File.ReadAllText(stampPath) != expectedStamp;
            }
            catch
            {
                return true;
            }
        }

        private static void DeleteDir(string path)
        {
            try
            {
                if (Directory.Exists(path))
                {
                    Directory.Delete(path, true);
                }
            }
            catch
            {
                try
                {
                    string backup = path + "_old_" + Guid.NewGuid().ToString("N").Substring(0, 8);
                    Directory.Move(path, backup);
                }
                catch { }
            }
        }

        private static void ExtractPayload(string installDir, LauncherSplash splash)
        {
            string tempZip = Path.Combine(
                Path.GetTempPath(),
                LauncherConfig.AppName + "-" + LauncherConfig.Version + "-" + Guid.NewGuid().ToString("N") + ".zip"
            );

            try
            {
                using (Stream source = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
                {
                    if (source == null)
                    {
                        throw new InvalidOperationException("Embedded payload.zip was not found.");
                    }
                    using (FileStream target = new FileStream(tempZip, FileMode.Create, FileAccess.Write))
                    {
                        PumpingCopy(source, target, splash);
                    }
                }

                using (ZipArchive archive = ZipFile.OpenRead(tempZip))
                {
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        ExtractEntry(entry, installDir, splash);
                    }
                }
            }
            finally
            {
                try { if (File.Exists(tempZip)) File.Delete(tempZip); } catch { }
            }
        }

        private static void ExtractEntry(ZipArchiveEntry entry, string installDir, LauncherSplash splash)
        {
            string relativePath = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
            if (string.IsNullOrWhiteSpace(relativePath)) return;

            string destination = Path.GetFullPath(Path.Combine(installDir, relativePath));
            string root = Path.GetFullPath(installDir + Path.DirectorySeparatorChar);
            if (!destination.StartsWith(root, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("Blocked unsafe payload path: " + entry.FullName);
            }

            if (string.IsNullOrEmpty(entry.Name))
            {
                Directory.CreateDirectory(destination);
                return;
            }

            string parent = Path.GetDirectoryName(destination);
            if (!string.IsNullOrEmpty(parent))
            {
                Directory.CreateDirectory(parent);
            }

            using (Stream input = entry.Open())
            using (FileStream output = new FileStream(destination, FileMode.Create, FileAccess.Write))
            {
                PumpingCopy(input, output, splash);
            }
        }

        private static void PumpingCopy(Stream input, Stream output, LauncherSplash splash)
        {
            byte[] buffer = new byte[1024 * 256];
            int read;
            long copied = 0;
            while ((read = input.Read(buffer, 0, buffer.Length)) > 0)
            {
                output.Write(buffer, 0, read);
                copied += read;
                if (copied >= 1024 * 1024)
                {
                    copied = 0;
                    if (splash != null)
                    {
                        splash.Pump();
                    }
                }
            }
        }

        private static string Quote(string value)
        {
            return "\"" + value.Replace("\"", "\\\"") + "\"";
        }
    }

    internal sealed class LauncherSplash : Form
    {
        private readonly System.Windows.Forms.Timer timer;
        private readonly Stopwatch clock;
        private readonly Image splashImage;
        private string stage;
        private string detail;
        private int frame;

        public LauncherSplash(string appName)
        {
            Text = appName;
            stage = "正在启动 " + appName;
            detail = "请稍候";
            clock = Stopwatch.StartNew();
            splashImage = LoadSplashImage();
            DoubleBuffered = true;
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.CenterScreen;
            TopMost = true;
            Width = 620;
            Height = 380;
            BackColor = Color.FromArgb(246, 249, 255);
            using (GraphicsPath formShape = RoundedRect(new Rectangle(0, 0, Width, Height), 30))
            {
                Region = new Region(formShape);
            }
            timer = new System.Windows.Forms.Timer();
            timer.Interval = 33;
            timer.Tick += delegate
            {
                frame = (frame + 1) % 360;
                Invalidate();
            };
            timer.Start();
        }

        public void SetStage(string nextStage, string nextDetail)
        {
            stage = string.IsNullOrWhiteSpace(nextStage) ? "正在启动" : nextStage;
            detail = string.IsNullOrWhiteSpace(nextDetail) ? "请稍候" : nextDetail;
            Invalidate();
            Pump();
        }

        public void Pump()
        {
            Application.DoEvents();
        }

        public void CloseSplash()
        {
            try
            {
                timer.Stop();
                if (splashImage != null) { splashImage.Dispose(); }
                Close();
                Dispose();
            }
            catch { }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            if (clock != null)
            {
                PaintLightSplash(g);
                return;
            }
            Rectangle bounds = new Rectangle(10, 10, Width - 20, Height - 20);
            using (GraphicsPath shadowPath = RoundedRect(new Rectangle(bounds.X, bounds.Y + 8, bounds.Width, bounds.Height), 24))
            using (SolidBrush shadow = new SolidBrush(Color.FromArgb(105, 6, 12, 24)))
            {
                g.FillPath(shadow, shadowPath);
            }
            using (GraphicsPath path = RoundedRect(bounds, 24))
            using (LinearGradientBrush bg = new LinearGradientBrush(bounds, Color.FromArgb(246, 23, 35, 53), Color.FromArgb(250, 17, 28, 43), LinearGradientMode.ForwardDiagonal))
            {
                g.FillPath(bg, path);
            }

            float cx = 112;
            float cy = 120;
            float radius = 46;
            using (Pen ring = new Pen(Color.FromArgb(48, 155, 203, 255), 1.5f))
            {
                g.DrawEllipse(ring, cx - radius, cy - radius, radius * 2, radius * 2);
                g.DrawEllipse(ring, cx - radius * 0.74f, cy - radius * 0.74f, radius * 1.48f, radius * 1.48f);
                g.DrawEllipse(ring, cx - radius * 0.46f, cy - radius * 0.46f, radius * 0.92f, radius * 0.92f);
            }
            using (Pen arc = new Pen(Color.FromArgb(220, 120, 215, 255), 4f))
            {
                arc.StartCap = LineCap.Round;
                arc.EndCap = LineCap.Round;
                g.DrawArc(arc, cx - radius, cy - radius, radius * 2, radius * 2, frame * 4, 115);
            }
            double angle = frame * 4 * Math.PI / 180.0;
            float dotX = cx + (float)Math.Cos(angle) * radius;
            float dotY = cy + (float)Math.Sin(angle) * radius;
            using (SolidBrush dot = new SolidBrush(Color.FromArgb(235, 255, 218, 121)))
            {
                g.FillEllipse(dot, dotX - 5, dotY - 5, 10, 10);
            }

            using (Font titleFont = new Font("Microsoft YaHei UI", 28, FontStyle.Bold))
            using (SolidBrush titleBrush = new SolidBrush(Color.FromArgb(238, 246, 255)))
            {
                g.DrawString(LauncherConfig.AppName, titleFont, titleBrush, new RectangleF(178, 72, 270, 48));
            }
            using (Font subtitleFont = new Font("Microsoft YaHei UI", 10, FontStyle.Regular))
            using (SolidBrush subtitleBrush = new SolidBrush(Color.FromArgb(172, 191, 210)))
            {
                g.DrawString("\u5c0f\u8bf4\u521b\u4f5c\u5de5\u4f5c\u53f0", subtitleFont, subtitleBrush, new RectangleF(180, 120, 290, 26));
            }
            using (Font stageFont = new Font("Microsoft YaHei UI", 12, FontStyle.Bold))
            using (SolidBrush stageBrush = new SolidBrush(Color.FromArgb(231, 239, 249)))
            {
                g.DrawString(stage, stageFont, stageBrush, new RectangleF(46, 204, 430, 30));
            }
            using (Font detailFont = new Font("Microsoft YaHei UI", 9, FontStyle.Regular))
            using (SolidBrush detailBrush = new SolidBrush(Color.FromArgb(150, 170, 190)))
            {
                g.DrawString(detail, detailFont, detailBrush, new RectangleF(46, 232, 430, 24));
            }

            RectangleF track = new RectangleF(46, 270, 428, 8);
            using (GraphicsPath trackPath = RoundedRect(Rectangle.Round(track), 4))
            using (SolidBrush trackBrush = new SolidBrush(Color.FromArgb(36, 255, 255, 255)))
            {
                g.FillPath(trackBrush, trackPath);
            }
            float barWidth = 110;
            float phase = (float)((clock.ElapsedMilliseconds % 1400) / 1400.0);
            float barX = track.Left + phase * (track.Width - barWidth);
            RectangleF barRect = new RectangleF(barX, track.Top, barWidth, track.Height);
            using (GraphicsPath barPath = RoundedRect(Rectangle.Round(barRect), 4))
            using (LinearGradientBrush bar = new LinearGradientBrush(barRect, Color.FromArgb(28, 100, 190, 255), Color.FromArgb(230, 136, 223, 255), LinearGradientMode.Horizontal))
            {
                g.FillPath(bar, barPath);
            }
        }

        private void PaintLightSplash(Graphics g)
        {
            if (clock != null)
            {
                PaintElegantLightSplash(g);
                return;
            }

            Rectangle bounds = new Rectangle(0, 0, Width, Height);
            using (LinearGradientBrush page = new LinearGradientBrush(bounds, Color.FromArgb(250, 253, 255), Color.FromArgb(232, 242, 255), LinearGradientMode.ForwardDiagonal))
            {
                g.FillRectangle(page, bounds);
            }
            using (SolidBrush blueGlow = new SolidBrush(Color.FromArgb(58, 112, 194, 255)))
            using (SolidBrush warmGlow = new SolidBrush(Color.FromArgb(40, 255, 210, 116)))
            {
                g.FillEllipse(blueGlow, 360, -68, 260, 180);
                g.FillEllipse(warmGlow, -70, 210, 220, 150);
            }

            Rectangle shell = new Rectangle(20, 20, Width - 40, Height - 40);
            using (GraphicsPath shellPath = RoundedRect(shell, 24))
            using (SolidBrush shellBrush = new SolidBrush(Color.FromArgb(238, 255, 255, 255)))
            {
                g.FillPath(shellBrush, shellPath);
            }
            using (GraphicsPath shellPath = RoundedRect(shell, 24))
            using (Pen border = new Pen(Color.FromArgb(150, 215, 226, 242), 1f))
            {
                g.DrawPath(border, shellPath);
            }

            RectangleF logoRect = new RectangleF(48, 62, 72, 72);
            using (LinearGradientBrush logoBrush = new LinearGradientBrush(Rectangle.Round(logoRect), Color.FromArgb(94, 164, 255), Color.FromArgb(126, 226, 210), LinearGradientMode.ForwardDiagonal))
            {
                g.FillEllipse(logoBrush, logoRect);
            }
            using (Pen logoRing = new Pen(Color.FromArgb(180, 255, 255, 255), 2f))
            {
                g.DrawEllipse(logoRing, logoRect);
            }
            using (Font logoFont = new Font("Microsoft YaHei UI", 25, FontStyle.Bold))
            using (SolidBrush logoText = new SolidBrush(Color.White))
            using (StringFormat centered = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
            {
                g.DrawString("灵", logoFont, logoText, logoRect, centered);
            }

            using (Font titleFont = new Font("Microsoft YaHei UI", 25, FontStyle.Bold))
            using (SolidBrush titleBrush = new SolidBrush(Color.FromArgb(36, 55, 80)))
            {
                g.DrawString(LauncherConfig.AppName, titleFont, titleBrush, new RectangleF(136, 68, 154, 42));
            }
            using (Font subtitleFont = new Font("Microsoft YaHei UI", 10, FontStyle.Regular))
            using (SolidBrush subtitleBrush = new SolidBrush(Color.FromArgb(103, 126, 154)))
            {
                g.DrawString("\u5c0f\u8bf4\u521b\u4f5c\u5de5\u4f5c\u53f0", subtitleFont, subtitleBrush, new RectangleF(138, 112, 180, 24));
            }

            Rectangle preview = new Rectangle(312, 58, 178, 128);
            using (GraphicsPath previewPath = RoundedRect(preview, 16))
            using (SolidBrush previewBrush = new SolidBrush(Color.FromArgb(245, 248, 252, 255)))
            {
                g.FillPath(previewBrush, previewPath);
            }
            using (GraphicsPath previewPath = RoundedRect(preview, 16))
            using (Pen previewBorder = new Pen(Color.FromArgb(170, 216, 229, 246), 1f))
            {
                g.DrawPath(previewBorder, previewPath);
            }
            using (SolidBrush sidebar = new SolidBrush(Color.FromArgb(230, 238, 248, 255)))
            {
                g.FillRectangle(sidebar, 326, 76, 34, 92);
            }
            using (SolidBrush accent = new SolidBrush(Color.FromArgb(112, 165, 255)))
            using (SolidBrush pale = new SolidBrush(Color.FromArgb(205, 224, 248)))
            using (Pen line = new Pen(Color.FromArgb(178, 199, 222), 3f))
            {
                g.FillEllipse(accent, 335, 86, 12, 12);
                g.FillEllipse(pale, 335, 110, 12, 12);
                g.FillEllipse(pale, 335, 134, 12, 12);
                line.StartCap = LineCap.Round;
                line.EndCap = LineCap.Round;
                g.DrawLine(line, 378, 86, 462, 86);
                g.DrawLine(line, 378, 108, 446, 108);
                g.DrawLine(line, 378, 130, 468, 130);
                g.DrawLine(line, 378, 152, 430, 152);
            }

            float pulse = (float)(0.5 + 0.5 * Math.Sin(clock.ElapsedMilliseconds / 260.0));
            using (SolidBrush pulseBrush = new SolidBrush(Color.FromArgb((int)(90 + pulse * 70), 97, 173, 255)))
            {
                g.FillEllipse(pulseBrush, 470, 70, 8, 8);
            }

            using (Font stageFont = new Font("Microsoft YaHei UI", 12, FontStyle.Bold))
            using (SolidBrush stageBrush = new SolidBrush(Color.FromArgb(55, 71, 93)))
            {
                g.DrawString(stage, stageFont, stageBrush, new RectangleF(48, 218, 420, 30));
            }
            using (Font detailFont = new Font("Microsoft YaHei UI", 9, FontStyle.Regular))
            using (SolidBrush detailBrush = new SolidBrush(Color.FromArgb(122, 143, 166)))
            {
                g.DrawString(detail, detailFont, detailBrush, new RectangleF(48, 246, 420, 24));
            }

            RectangleF ringRect = new RectangleF(470, 222, 28, 28);
            using (Pen ringTrack = new Pen(Color.FromArgb(215, 225, 238), 3f))
            using (Pen ringArc = new Pen(Color.FromArgb(94, 164, 255), 3f))
            {
                ringArc.StartCap = LineCap.Round;
                ringArc.EndCap = LineCap.Round;
                g.DrawEllipse(ringTrack, ringRect);
                g.DrawArc(ringArc, ringRect, frame * 5, 110);
            }

            RectangleF track = new RectangleF(48, 288, 464, 7);
            using (GraphicsPath trackPath = RoundedRect(Rectangle.Round(track), 4))
            using (SolidBrush trackBrush = new SolidBrush(Color.FromArgb(226, 233, 243)))
            {
                g.FillPath(trackBrush, trackPath);
            }
            float barWidth = 146;
            float phase = (float)((clock.ElapsedMilliseconds % 1200) / 1200.0);
            float barX = track.Left + phase * (track.Width - barWidth);
            RectangleF barRect = new RectangleF(barX, track.Top, barWidth, track.Height);
            using (GraphicsPath barPath = RoundedRect(Rectangle.Round(barRect), 4))
            using (LinearGradientBrush bar = new LinearGradientBrush(barRect, Color.FromArgb(30, 120, 182, 255), Color.FromArgb(235, 92, 168, 255), LinearGradientMode.Horizontal))
            {
                bar.SetBlendTriangularShape(0.5f);
                g.FillPath(bar, barPath);
            }
        }

        private void PaintElegantLightSplash(Graphics g)
        {
            if (splashImage != null)
            {
                PaintAnimeSplash(g);
                return;
            }

            Rectangle bounds = new Rectangle(0, 0, Width, Height);
            using (LinearGradientBrush page = new LinearGradientBrush(bounds, Color.FromArgb(249, 245, 239), Color.FromArgb(31, 42, 61), LinearGradientMode.ForwardDiagonal))
            {
                page.InterpolationColors = new ColorBlend
                {
                    Positions = new[] { 0f, 0.38f, 1f },
                    Colors = new[]
                    {
                        Color.FromArgb(249, 245, 239),
                        Color.FromArgb(230, 236, 242),
                        Color.FromArgb(31, 42, 61)
                    }
                };
                g.FillRectangle(page, bounds);
            }
            using (SolidBrush tealGlow = new SolidBrush(Color.FromArgb(42, 13, 194, 178)))
            using (SolidBrush warmGlow = new SolidBrush(Color.FromArgb(40, 255, 185, 126)))
            {
                g.FillEllipse(tealGlow, 116, 54, 476, 260);
                g.FillEllipse(warmGlow, -70, 24, 260, 210);
            }

            Rectangle shell = new Rectangle(22, 20, Width - 44, Height - 40);
            using (GraphicsPath shadowPath = RoundedRect(new Rectangle(shell.X, shell.Y + 8, shell.Width, shell.Height), 28))
            using (SolidBrush shadowBrush = new SolidBrush(Color.FromArgb(68, 8, 14, 25)))
            {
                g.FillPath(shadowBrush, shadowPath);
            }
            using (GraphicsPath shellPath = RoundedRect(shell, 28))
            using (LinearGradientBrush shellBrush = new LinearGradientBrush(shell, Color.FromArgb(255, 252, 246), Color.FromArgb(50, 63, 84), LinearGradientMode.ForwardDiagonal))
            {
                shellBrush.InterpolationColors = new ColorBlend
                {
                    Positions = new[] { 0f, 0.54f, 1f },
                    Colors = new[]
                    {
                        Color.FromArgb(236, 255, 252, 246),
                        Color.FromArgb(225, 229, 236, 242),
                        Color.FromArgb(230, 50, 63, 84)
                    }
                };
                g.FillPath(shellBrush, shellPath);
            }
            using (GraphicsPath shellPath = RoundedRect(shell, 28))
            using (Pen border = new Pen(Color.FromArgb(120, 255, 255, 255), 1f))
            {
                g.DrawPath(border, shellPath);
            }

            DrawStudioWindowLight(g);

            Rectangle logoRect = new Rectangle(61, 178, 74, 74);
            using (GraphicsPath logoPath = RoundedRect(logoRect, 22))
            using (LinearGradientBrush logoBrush = new LinearGradientBrush(logoRect, Color.FromArgb(21, 216, 194), Color.FromArgb(29, 44, 65), LinearGradientMode.ForwardDiagonal))
            {
                logoBrush.InterpolationColors = new ColorBlend
                {
                    Positions = new[] { 0f, 0.52f, 1f },
                    Colors = new[]
                    {
                        Color.FromArgb(21, 216, 194),
                        Color.FromArgb(13, 128, 133),
                        Color.FromArgb(29, 44, 65)
                    }
                };
                g.FillPath(logoBrush, logoPath);
            }
            RectangleF logoRingRect = new RectangleF(logoRect.Left + 8, logoRect.Top + 8, 58, 58);
            using (Pen logoRing = new Pen(Color.FromArgb(70, 255, 255, 255), 2f))
            using (Pen logoArc = new Pen(Color.FromArgb(230, 255, 230, 186), 3f))
            {
                logoArc.StartCap = LineCap.Round;
                logoArc.EndCap = LineCap.Round;
                g.DrawArc(logoRing, logoRingRect, 35, 190);
                g.DrawArc(logoArc, logoRingRect, frame * 4, 84);
            }
            DrawTealFlame(g, 122, 188, 15, 175, frame / 12.0);
            using (Font logoFont = new Font("Microsoft YaHei UI", 25, FontStyle.Bold))
            using (SolidBrush logoText = new SolidBrush(Color.White))
            using (StringFormat centered = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
            {
                g.DrawString("\u7075", logoFont, logoText, logoRect, centered);
            }

            using (Font titleFont = new Font("Microsoft YaHei UI", 28, FontStyle.Bold))
            using (SolidBrush titleBrush = new SolidBrush(Color.FromArgb(33, 45, 63)))
            {
                g.DrawString(LauncherConfig.AppName, titleFont, titleBrush, new RectangleF(152, 181, 180, 44));
            }
            using (Font subtitleFont = new Font("Microsoft YaHei UI", 10, FontStyle.Regular))
            using (SolidBrush subtitleBrush = new SolidBrush(Color.FromArgb(82, 94, 111)))
            {
                g.DrawString("\u5c0f\u8bf4\u521b\u4f5c\u5de5\u4f5c\u53f0", subtitleFont, subtitleBrush, new RectangleF(154, 224, 210, 24));
            }
            DrawAccentDots(g, 154, 253);

            DrawSoftWorkspacePreview(g);

            float pulse = (float)(0.5 + 0.5 * Math.Sin(clock.ElapsedMilliseconds / 260.0));
            using (Font stageFont = new Font("Microsoft YaHei UI", 13, FontStyle.Bold))
            using (SolidBrush stageBrush = new SolidBrush(Color.FromArgb(32, 43, 59)))
            {
                g.DrawString(stage, stageFont, stageBrush, new RectangleF(54, 294, 430, 30));
            }
            using (Font detailFont = new Font("Microsoft YaHei UI", 9, FontStyle.Regular))
            using (SolidBrush detailBrush = new SolidBrush(Color.FromArgb(83, 96, 114)))
            {
                g.DrawString(detail, detailFont, detailBrush, new RectangleF(54, 322, 430, 24));
            }

            RectangleF ringRect = new RectangleF(520, 296, 30, 30);
            using (Pen ringTrack = new Pen(Color.FromArgb(125, 159, 174, 191), 3f))
            using (Pen ringArc = new Pen(Color.FromArgb(6, 183, 169), 3f))
            {
                ringArc.StartCap = LineCap.Round;
                ringArc.EndCap = LineCap.Round;
                g.DrawEllipse(ringTrack, ringRect);
                g.DrawArc(ringArc, ringRect, frame * 4, 115);
            }
            using (SolidBrush pulseBrush = new SolidBrush(Color.FromArgb((int)(76 + pulse * 96), 244, 159, 91)))
            {
                g.FillEllipse(pulseBrush, 544, 290, 8, 8);
            }

            RectangleF track = new RectangleF(54, 350, 512, 7);
            using (GraphicsPath trackPath = RoundedRect(Rectangle.Round(track), 4))
            using (SolidBrush trackBrush = new SolidBrush(Color.FromArgb(72, 44, 58, 76)))
            {
                g.FillPath(trackBrush, trackPath);
            }
            float barWidth = 170;
            float phase = (float)((clock.ElapsedMilliseconds % 1416) / 1416.0);
            float barX = track.Left + phase * (track.Width - barWidth);
            RectangleF barRect = new RectangleF(barX, track.Top, barWidth, track.Height);
            using (GraphicsPath barPath = RoundedRect(Rectangle.Round(barRect), 4))
            using (LinearGradientBrush bar = new LinearGradientBrush(barRect, Color.FromArgb(20, 13, 194, 178), Color.FromArgb(46, 244, 159, 91), LinearGradientMode.Horizontal))
            {
                bar.SetBlendTriangularShape(0.5f);
                g.FillPath(bar, barPath);
            }
        }

        private static void DrawStudioWindowLight(Graphics g)
        {
            Rectangle window = new Rectangle(43, 42, 138, 118);
            using (GraphicsPath path = RoundedRect(window, 16))
            using (LinearGradientBrush pane = new LinearGradientBrush(window, Color.FromArgb(170, 255, 250, 238), Color.FromArgb(60, 255, 206, 164), LinearGradientMode.ForwardDiagonal))
            {
                g.FillPath(pane, path);
            }
            using (Pen slat = new Pen(Color.FromArgb(78, 78, 84, 98), 5f))
            {
                slat.StartCap = LineCap.Round;
                slat.EndCap = LineCap.Round;
                for (int y = 55; y < 150; y += 14)
                {
                    g.DrawLine(slat, 52, y, 172, y - 8);
                }
            }
            using (GraphicsPath ray = new GraphicsPath())
            using (LinearGradientBrush rayBrush = new LinearGradientBrush(new Rectangle(46, 74, 266, 132), Color.FromArgb(84, 255, 229, 191), Color.FromArgb(0, 255, 229, 191), LinearGradientMode.Horizontal))
            {
                ray.AddPolygon(new[]
                {
                    new PointF(50, 74),
                    new PointF(285, 120),
                    new PointF(312, 205),
                    new PointF(64, 130),
                });
                g.FillPath(rayBrush, ray);
            }
        }


        private static Image LoadSplashImage()
        {
            Assembly assembly = Assembly.GetExecutingAssembly();
            foreach (string name in assembly.GetManifestResourceNames())
            {
                if (!name.EndsWith("startup_anime.jpg", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }
                using (Stream stream = assembly.GetManifestResourceStream(name))
                {
                    if (stream == null)
                    {
                        continue;
                    }
                    using (Bitmap bitmap = new Bitmap(stream))
                    {
                        return new Bitmap(bitmap);
                    }
                }
            }
            return null;
        }

        private static void DrawSplashImageCover(Graphics g, Image image, Rectangle target)
        {
            if (image == null || image.Width <= 0 || image.Height <= 0)
            {
                return;
            }
            float scale = Math.Max(target.Width / (float)image.Width, target.Height / (float)image.Height);
            float drawWidth = image.Width * scale;
            float drawHeight = image.Height * scale;
            RectangleF destination = new RectangleF(
                target.Left + (target.Width - drawWidth) / 2f,
                target.Top + (target.Height - drawHeight) / 2f,
                drawWidth,
                drawHeight
            );
            g.DrawImage(image, destination);
        }

        private static void DrawAnimeVignette(Graphics g, Rectangle bounds)
        {
            using (GraphicsPath path = RoundedRect(bounds, 30))
            using (PathGradientBrush vignette = new PathGradientBrush(path))
            {
                vignette.CenterPoint = new PointF(bounds.Left + bounds.Width * 0.64f, bounds.Top + bounds.Height * 0.42f);
                vignette.CenterColor = Color.FromArgb(0, 7, 11, 18);
                vignette.SurroundColors = new[] { Color.FromArgb(112, 7, 11, 18) };
                g.FillPath(vignette, path);
            }
        }

        private void PaintAnimeSplash(Graphics g)
        {
            Rectangle bounds = new Rectangle(0, 0, Width, Height);
            using (GraphicsPath clip = RoundedRect(bounds, 30))
            using (Region oldClip = g.Clip)
            {
                g.SetClip(clip);
                DrawSplashImageCover(g, splashImage, bounds);

                using (SolidBrush wash = new SolidBrush(Color.FromArgb(64, 7, 11, 18)))
                {
                    g.FillRectangle(wash, bounds);
                }
                DrawAnimeVignette(g, bounds);
                Rectangle textGlow = new Rectangle(18, 190, 332, 176);
                using (GraphicsPath glowPath = RoundedRect(textGlow, 28))
                using (PathGradientBrush glow = new PathGradientBrush(glowPath))
                {
                    glow.CenterPoint = new PointF(textGlow.Left + 78, textGlow.Bottom - 68);
                    glow.CenterColor = Color.FromArgb(145, 7, 11, 18);
                    glow.SurroundColors = new[] { Color.FromArgb(0, 7, 11, 18) };
                    g.FillPath(glow, glowPath);
                }
                DrawAnimeBrand(g);
                DrawAnimeStatus(g);
                DrawAnimeSweep(g);
                g.SetClip(oldClip, CombineMode.Replace);
            }
            using (GraphicsPath shell = RoundedRect(bounds, 30))
            using (Pen border = new Pen(Color.FromArgb(115, 255, 255, 255), 1f))
            {
                g.DrawPath(border, shell);
            }
        }

        private void DrawAnimeBrand(Graphics g)
        {
            using (Font titleFont = new Font("Microsoft YaHei UI", 32, FontStyle.Bold))
            using (SolidBrush titleBrush = new SolidBrush(Color.FromArgb(255, 252, 246)))
            {
                g.DrawString(LauncherConfig.AppName, titleFont, titleBrush, new RectangleF(42, 224, 230, 54));
            }
            using (Font subtitleFont = new Font("Microsoft YaHei UI", 10, FontStyle.Regular))
            using (SolidBrush subtitleBrush = new SolidBrush(Color.FromArgb(222, 220, 233, 232)))
            {
                g.DrawString("\u5c0f\u8bf4\u521b\u4f5c\u5de5\u4f5c\u53f0", subtitleFont, subtitleBrush, new RectangleF(45, 273, 240, 24));
            }
            float flameX = 137 + (float)Math.Sin(frame / 14.0) * 2f;
            DrawTealFlame(g, flameX, 227, 13, 210, frame / 10.0);
        }

        private void DrawAnimeStatus(Graphics g)
        {
            using (Font stageFont = new Font("Microsoft YaHei UI", 12, FontStyle.Bold))
            using (SolidBrush stageBrush = new SolidBrush(Color.FromArgb(235, 246, 250, 250)))
            {
                g.DrawString(stage, stageFont, stageBrush, new RectangleF(44, 304, 360, 27));
            }
            using (Font detailFont = new Font("Microsoft YaHei UI", 9, FontStyle.Regular))
            using (SolidBrush detailBrush = new SolidBrush(Color.FromArgb(210, 201, 218, 220)))
            {
                g.DrawString(detail, detailFont, detailBrush, new RectangleF(44, 329, 360, 22));
            }

            float pulse = (float)(0.5 + 0.5 * Math.Sin(clock.ElapsedMilliseconds / 240.0));
            RectangleF ringRect = new RectangleF(534, 304, 30, 30);
            using (Pen ringTrack = new Pen(Color.FromArgb(90, 235, 238, 241), 3f))
            using (Pen ringArc = new Pen(Color.FromArgb(230, 21, 223, 201), 3f))
            {
                ringArc.StartCap = LineCap.Round;
                ringArc.EndCap = LineCap.Round;
                g.DrawEllipse(ringTrack, ringRect);
                g.DrawArc(ringArc, ringRect, frame * 4, 120);
            }
            using (SolidBrush pulseBrush = new SolidBrush(Color.FromArgb((int)(90 + pulse * 110), 246, 147, 79)))
            {
                g.FillEllipse(pulseBrush, 559, 299, 8, 8);
            }

            RectangleF track = new RectangleF(42, 357, 536, 7);
            using (GraphicsPath trackPath = RoundedRect(Rectangle.Round(track), 4))
            using (SolidBrush trackBrush = new SolidBrush(Color.FromArgb(72, 244, 248, 250)))
            {
                g.FillPath(trackBrush, trackPath);
            }
            float barWidth = 176;
            float phase = (float)((clock.ElapsedMilliseconds % 1488) / 1488.0);
            float barX = track.Left + phase * (track.Width - barWidth);
            RectangleF barRect = new RectangleF(barX, track.Top, barWidth, track.Height);
            using (GraphicsPath barPath = RoundedRect(Rectangle.Round(barRect), 4))
            using (LinearGradientBrush bar = new LinearGradientBrush(barRect, Color.FromArgb(22, 21, 223, 201), Color.FromArgb(58, 246, 147, 79), LinearGradientMode.Horizontal))
            {
                bar.SetBlendTriangularShape(0.5f);
                g.FillPath(bar, barPath);
            }
        }

        private void DrawAnimeSweep(Graphics g)
        {
            float sweepX = -140 + (float)((clock.ElapsedMilliseconds % 2160) / 2160.0) * (Width + 280);
            RectangleF sweepRect = new RectangleF(sweepX - 60, 0, 120, Height);
            using (LinearGradientBrush sweep = new LinearGradientBrush(sweepRect, Color.FromArgb(0, 255, 255, 255), Color.FromArgb(34, 255, 255, 255), LinearGradientMode.Horizontal))
            {
                sweep.SetBlendTriangularShape(0.5f);
                g.FillRectangle(sweep, sweepRect);
            }
        }

        private static void DrawAccentDots(Graphics g, float left, float top)
        {
            using (SolidBrush teal = new SolidBrush(Color.FromArgb(160, 9, 161, 151)))
            using (SolidBrush warm = new SolidBrush(Color.FromArgb(150, 229, 137, 71)))
            using (SolidBrush slate = new SolidBrush(Color.FromArgb(135, 55, 70, 96)))
            {
                g.FillEllipse(teal, left, top, 10, 10);
                g.FillEllipse(warm, left + 18, top + 1, 8, 8);
                g.FillEllipse(slate, left + 34, top, 10, 10);
            }
        }

        private void DrawSoftWorkspacePreview(Graphics g)
        {
            Rectangle preview = new Rectangle(346, 54, 222, 178);
            using (GraphicsPath shadowPath = RoundedRect(new Rectangle(preview.X, preview.Y + 7, preview.Width, preview.Height), 22))
            using (SolidBrush shadow = new SolidBrush(Color.FromArgb(54, 8, 14, 25)))
            {
                g.FillPath(shadow, shadowPath);
            }
            using (GraphicsPath previewPath = RoundedRect(preview, 20))
            using (LinearGradientBrush room = new LinearGradientBrush(preview, Color.FromArgb(242, 231, 216), Color.FromArgb(27, 36, 54), LinearGradientMode.ForwardDiagonal))
            {
                room.InterpolationColors = new ColorBlend
                {
                    Positions = new[] { 0f, 0.42f, 1f },
                    Colors = new[]
                    {
                        Color.FromArgb(246, 242, 231, 216),
                        Color.FromArgb(238, 107, 118, 139),
                        Color.FromArgb(246, 27, 36, 54)
                    }
                };
                g.FillPath(room, previewPath);
            }
            using (GraphicsPath previewPath = RoundedRect(preview, 20))
            using (Pen previewBorder = new Pen(Color.FromArgb(90, 255, 255, 255), 1f))
            {
                g.DrawPath(previewBorder, previewPath);
            }

            DrawPreviewBlinds(g, preview);
            DrawPreviewArtist(g, preview);
            DrawPreviewDesk(g, preview);

            float sweepX = preview.Left - 70 + (float)((clock.ElapsedMilliseconds % 1500) / 1500.0) * (preview.Width + 140);
            RectangleF sweepRect = new RectangleF(sweepX - 44, preview.Top, 88, preview.Height);
            using (GraphicsPath clip = RoundedRect(preview, 20))
            using (LinearGradientBrush sweep = new LinearGradientBrush(sweepRect, Color.FromArgb(0, 255, 255, 255), Color.FromArgb(62, 255, 255, 255), LinearGradientMode.Horizontal))
            using (Region oldClip = g.Clip)
            {
                sweep.SetBlendTriangularShape(0.5f);
                g.SetClip(clip);
                g.FillRectangle(sweep, sweepRect);
                g.SetClip(oldClip, CombineMode.Replace);
            }
        }

        private static void DrawPreviewBlinds(Graphics g, Rectangle preview)
        {
            using (GraphicsPath pane = RoundedRect(new Rectangle(preview.Left + 14, preview.Top + 14, 82, 72), 12))
            using (SolidBrush light = new SolidBrush(Color.FromArgb(112, 255, 241, 218)))
            {
                g.FillPath(light, pane);
            }
            using (Pen slat = new Pen(Color.FromArgb(86, 54, 57, 72), 4f))
            {
                slat.StartCap = LineCap.Round;
                slat.EndCap = LineCap.Round;
                for (int index = 0; index < 6; index++)
                {
                    float y = preview.Top + 26 + index * 10;
                    g.DrawLine(slat, preview.Left + 22, y, preview.Left + 90, y - 6);
                }
            }
        }

        private void DrawPreviewArtist(Graphics g, Rectangle preview)
        {
            float pulse = (float)(0.5 + 0.5 * Math.Sin(clock.ElapsedMilliseconds / 300.0));
            float cx = preview.Left + 142;
            float cy = preview.Top + 88;

            using (GraphicsPath hair = new GraphicsPath())
            using (SolidBrush hairBrush = new SolidBrush(Color.FromArgb(210, 20, 32, 47)))
            {
                hair.StartFigure();
                hair.AddBezier(cx - 46, cy + 58, cx - 68, cy - 28, cx - 8, cy - 62, cx + 28, cy - 45);
                hair.AddBezier(cx + 28, cy - 45, cx + 76, cy - 22, cx + 72, cy + 66, cx + 4, cy + 74);
                hair.AddBezier(cx + 4, cy + 74, cx - 24, cy + 78, cx - 30, cy + 66, cx - 46, cy + 58);
                hair.CloseFigure();
                g.FillPath(hairBrush, hair);
            }
            using (Pen hairGlow = new Pen(Color.FromArgb((int)(120 + pulse * 65), 25, 211, 191), 3f))
            {
                hairGlow.StartCap = LineCap.Round;
                hairGlow.EndCap = LineCap.Round;
                g.DrawLine(hairGlow, cx - 34, cy + 45, cx - 8, cy + 78);
                g.DrawLine(hairGlow, cx + 23, cy - 30, cx + 52, cy + 40);
            }
            using (SolidBrush skin = new SolidBrush(Color.FromArgb(245, 249, 220, 207)))
            using (SolidBrush shirt = new SolidBrush(Color.FromArgb(248, 246, 246, 244)))
            {
                g.FillEllipse(skin, cx - 21, cy - 35, 42, 48);
                using (GraphicsPath shirtPath = RoundedRect(Rectangle.Round(new RectangleF(cx - 34, cy + 9, 70, 54)), 18))
                {
                    g.FillPath(shirt, shirtPath);
                }
            }
            using (GraphicsPath leftHorn = new GraphicsPath())
            using (GraphicsPath rightHorn = new GraphicsPath())
            using (Pen hornDark = new Pen(Color.FromArgb(230, 7, 121, 126), 3f))
            using (Pen hornCore = new Pen(Color.FromArgb(230, 17, 221, 198), 2f))
            {
                hornDark.StartCap = LineCap.Round;
                hornDark.EndCap = LineCap.Round;
                hornCore.StartCap = LineCap.Round;
                hornCore.EndCap = LineCap.Round;
                leftHorn.AddBezier(cx - 12, cy - 37, cx - 42, cy - 68, cx - 52, cy - 20, cx - 72, cy - 25);
                rightHorn.AddBezier(cx + 8, cy - 39, cx + 32, cy - 78, cx + 37, cy - 22, cx + 55, cy - 31);
                g.DrawPath(hornDark, leftHorn);
                g.DrawPath(hornDark, rightHorn);
                g.DrawPath(hornCore, leftHorn);
                g.DrawPath(hornCore, rightHorn);
            }
            using (Pen eye = new Pen(Color.FromArgb(230, 230, 127, 56), 3f))
            using (Pen glasses = new Pen(Color.FromArgb(190, 34, 45, 64), 1f))
            {
                eye.StartCap = LineCap.Round;
                eye.EndCap = LineCap.Round;
                g.DrawLine(eye, cx - 11, cy - 11, cx - 4, cy - 10);
                g.DrawLine(eye, cx + 7, cy - 11, cx + 14, cy - 10);
                g.DrawEllipse(glasses, cx - 18, cy - 21, 16, 16);
                g.DrawEllipse(glasses, cx + 2, cy - 21, 16, 16);
                g.DrawLine(glasses, cx - 2, cy - 13, cx + 2, cy - 13);
            }
        }

        private void DrawPreviewDesk(Graphics g, Rectangle preview)
        {
            RectangleF desk = new RectangleF(preview.Left + 16, preview.Top + 120, 190, 46);
            using (GraphicsPath deskPath = RoundedRect(Rectangle.Round(desk), 14))
            using (LinearGradientBrush deskBrush = new LinearGradientBrush(desk, Color.FromArgb(205, 181, 125, 88), Color.FromArgb(218, 82, 63, 67), LinearGradientMode.ForwardDiagonal))
            {
                g.FillPath(deskBrush, deskPath);
            }
            RectangleF tablet = new RectangleF(preview.Left + 86, preview.Top + 126, 82, 34);
            using (GraphicsPath tabletPath = RoundedRect(Rectangle.Round(tablet), 7))
            using (SolidBrush tabletBrush = new SolidBrush(Color.FromArgb(230, 37, 46, 61)))
            {
                g.FillPath(tabletBrush, tabletPath);
            }
            using (GraphicsPath screenPath = RoundedRect(Rectangle.Round(new RectangleF(tablet.Left + 8, tablet.Top + 6, tablet.Width - 16, tablet.Height - 13)), 4))
            using (SolidBrush screenBrush = new SolidBrush(Color.FromArgb(150, 86, 104, 124)))
            {
                g.FillPath(screenBrush, screenPath);
            }
            using (Pen stylus = new Pen(Color.FromArgb(220, 25, 31, 43), 3f))
            {
                stylus.StartCap = LineCap.Round;
                stylus.EndCap = LineCap.Round;
                g.DrawLine(stylus, tablet.Left - 8, tablet.Top + 4, tablet.Left + 8, tablet.Bottom + 4);
            }
            using (SolidBrush cup = new SolidBrush(Color.FromArgb(235, 255, 250, 239)))
            using (SolidBrush coffee = new SolidBrush(Color.FromArgb(210, 92, 65, 54)))
            {
                g.FillEllipse(cup, preview.Left + 35, preview.Top + 132, 30, 18);
                g.FillEllipse(coffee, preview.Left + 41, preview.Top + 136, 18, 8);
            }
            DrawTealFlame(g, preview.Left + 184, preview.Top + 128, 18, 210, frame / 9.0);
        }

        private static void DrawTealFlame(Graphics g, float cx, float cy, float size, int alpha, double phase)
        {
            float wiggle = (float)Math.Sin(phase) * size * 0.12f;
            using (GraphicsPath flame = new GraphicsPath())
            using (SolidBrush outer = new SolidBrush(Color.FromArgb(alpha, 8, 205, 187)))
            using (SolidBrush inner = new SolidBrush(Color.FromArgb(Math.Min(255, alpha + 20), 112, 255, 229)))
            {
                flame.StartFigure();
                flame.AddBezier(cx, cy - size - wiggle, cx + size * 0.84f, cy - size * 0.42f, cx + size * 0.25f, cy + size * 0.22f, cx + size * 0.62f, cy + size * 0.78f);
                flame.AddBezier(cx + size * 0.62f, cy + size * 0.78f, cx + size * 0.1f, cy + size * 0.44f, cx - size * 0.1f, cy + size * 1.02f, cx - size * 0.72f, cy + size * 0.46f);
                flame.AddBezier(cx - size * 0.72f, cy + size * 0.46f, cx - size * 0.36f, cy + size * 0.22f, cx - size * 0.78f, cy - size * 0.42f, cx, cy - size - wiggle);
                flame.CloseFigure();
                g.FillPath(outer, flame);
                g.FillEllipse(inner, cx - size * 0.16f, cy - size * 0.24f, size * 0.32f, size * 0.48f);
            }
        }

        private static GraphicsPath RoundedRect(Rectangle rect, int radius)
        {
            GraphicsPath path = new GraphicsPath();
            int diameter = radius * 2;
            Rectangle arc = new Rectangle(rect.Location, new Size(diameter, diameter));
            path.AddArc(arc, 180, 90);
            arc.X = rect.Right - diameter;
            path.AddArc(arc, 270, 90);
            arc.Y = rect.Bottom - diameter;
            path.AddArc(arc, 0, 90);
            arc.X = rect.Left;
            path.AddArc(arc, 90, 90);
            path.CloseFigure();
            return path;
        }
    }
}
