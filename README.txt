================================================================
 CDGC MCP Server
 Informatica Cloud Data Governance & Catalog — MCP Integration
================================================================

This MCP server exposes the Informatica CDGC, Data Marketplace,
and IDMC APIs as tools for use with any MCP-compatible AI client
(Claude Desktop, Claude Code, Cursor, etc.).


----------------------------------------------------------------
 FILES
----------------------------------------------------------------

  server.py            - The MCP server
  auth.py              - Informatica session/auth management
  query_examples.md    - Example CDGC search queries (used by AI)
  requirements.txt     - Python dependencies
  credentials.env      - Your credentials (you create this —
                         see credentials.env.example for format)


----------------------------------------------------------------
 PREREQUISITES
----------------------------------------------------------------

  1. Python 3.10 or later
     Download: https://www.python.org/downloads/
     Verify:   python --version

  2. An Informatica Intelligent Data Management Cloud (IDMC) account
     with access to CDGC (Cloud Data Governance & Catalog).

  3. Your Informatica pod name (e.g. "dm-us", "usw3", "eu1", etc.)
     You can find this in your IDMC login URL:
       https://<pod>.informaticacloud.com


----------------------------------------------------------------
 INSTALLATION
----------------------------------------------------------------

Step 1 — Copy the server files to a folder on your machine.
         Example: C:\Tools\CDGC-MCP-Server\

Step 2 — Open a terminal, navigate to that folder, and install
         the required Python packages:

           pip install -r requirements.txt

Step 3 — Create your credentials file.
         Copy credentials.env.example to credentials.env
         and fill in your values:

           pod=dm-us
           username=your_informatica_username
           password=your_informatica_password

         The pod value is the prefix from your IDMC login URL.
         Example: if you log in at dm-us.informaticacloud.com
         then pod=dm-us

         IMPORTANT: Keep credentials.env private.
                    Do not share it or commit it to source control.

Step 4 — Test the server runs without errors:

           python server.py

         The server will start silently and appear to hang — this is
         correct. MCP servers communicate over stdio, so there is no
         startup message. If the server crashed (missing dependency,
         bad credentials file, etc.) you would see an error message.
         Silence means it started successfully.

         Press Ctrl+C to stop it.


----------------------------------------------------------------
 CONNECTING TO CLAUDE DESKTOP
----------------------------------------------------------------

Step 1 — Find or create the Claude Desktop config file at:

           Windows:  %APPDATA%\Claude\claude_desktop_config.json
           macOS:    ~/Library/Application Support/Claude/claude_desktop_config.json

Step 2 — Add the following to the config file, replacing the
         path with the actual location of server.py on your machine:

           {
             "mcpServers": {
               "cdgc": {
                 "command": "python",
                 "args": ["C:/Tools/CDGC-MCP-Server/server.py"]
               }
             }
           }

         If claude_desktop_config.json already has other entries,
         add only the "cdgc" block inside the existing "mcpServers"
         section — do not replace the whole file.

Step 3 — Restart Claude Desktop.

Step 4 — Verify the connection. In Claude Desktop, open a new
         conversation and ask:
           "Which Snowflake catalog sources do I have?"

         Claude should call the CDGC tools and return results from
         your catalog.


----------------------------------------------------------------
 CONNECTING TO CLAUDE CODE (VS Code / CLI)
----------------------------------------------------------------

Step 1 — Open your Claude Code settings file at:

           Windows:  %USERPROFILE%\.claude\settings.json
           macOS:    ~/.claude/settings.json

Step 2 — Add the following, replacing the path with the actual
         location of server.py:

           {
             "mcpServers": {
               "cdgc": {
                 "command": "python",
                 "args": ["C:/Tools/CDGC-MCP-Server/server.py"]
               }
             }
           }

Step 3 — Reload the MCP connection. In the Claude Code chat, run:

           /mcp

         The server should appear as connected.

Step 4 — (Optional) To allow CDGC tool calls without being prompted
         for approval each time, add this to settings.json:

           {
             "permissions": {
               "allow": ["mcp__cdgc__*"]
             }
           }


----------------------------------------------------------------
 TROUBLESHOOTING
----------------------------------------------------------------

"python server.py produces no output"
  → This is normal. The server started successfully.
    Only error messages indicate a problem.

"credentials.env must contain: pod, username, password"
  → credentials.env is missing or has the wrong key names.
    Check spelling — all lowercase: pod, username, password.

"Login failed 401"
  → Username or password is incorrect. Verify you can log in
    at https://<pod>.informaticacloud.com directly.

"Login failed 404" or connection refused
  → The pod value is wrong. Double-check your IDMC login URL.

Server connects but tool calls return errors
  → Your IDMC user may not have CDGC API access. Contact your
    Informatica administrator to verify API permissions.

Claude Desktop doesn't show the server as connected
  → Confirm the path in claude_desktop_config.json is correct
    and uses forward slashes (or escaped backslashes on Windows).
  → Confirm Python is on your system PATH by running:
      python --version
    in a new terminal window.


----------------------------------------------------------------
 NOTES
----------------------------------------------------------------

- The server automatically re-authenticates when the session
  token expires — no manual intervention needed.

- Search query examples are bundled in query_examples.md and
  are automatically consulted by the AI when building searches.
  To add your own examples, edit that file directly.

- This server supports any MCP-compatible client, not just Claude.

================================================================
