"""
Enhanced AI Accounting Agent that properly uses MCP server for complex prompts
"""

import json
import logging
import asyncio
import subprocess
import os
from typing import Dict, List, Any, AsyncGenerator, Optional
from openai import OpenAI
import tempfile

logger = logging.getLogger(__name__)

class MCPAccountingClient:
    """Client that communicates with the MCP accounting server"""
    
    def __init__(self):
        self.process = None
        self.tools = []
        self.connected = False
        
    async def connect(self) -> bool:
        """Connect to the MCP server"""
        try:
            # Get the path to the MCP server
            mcp_server_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "mcp_server", "server.py")
            
            if not os.path.exists(mcp_server_path):
                logger.error(f"MCP server not found at {mcp_server_path}")
                return False
            
            # Start the MCP server process
            self.process = await asyncio.create_subprocess_exec(
                "python", mcp_server_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Send initialize request
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "sampling": {}
                    },
                    "clientInfo": {
                        "name": "accounting-agent",
                        "version": "1.0.0"
                    }
                }
            }
            
            await self._send_request(init_request)
            init_response = await self._read_response()
            
            if init_response.get("error"):
                logger.error(f"MCP initialization failed: {init_response['error']}")
                return False
            
            # Send initialized notification
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            await self._send_request(initialized_notification)
            
            # Get available tools
            tools_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list"
            }
            
            await self._send_request(tools_request)
            tools_response = await self._read_response()
            
            if tools_response.get("result"):
                self.tools = tools_response["result"]["tools"]
                logger.info(f"Connected to MCP server with {len(self.tools)} tools")
                self.connected = True
                return True
            else:
                logger.error("Failed to get tools from MCP server")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the MCP server"""
        if self.process:
            self.process.terminate()
            await self.process.wait()
            self.process = None
        self.connected = False
        self.tools = []
    
    async def _send_request(self, request: Dict[str, Any]):
        """Send a JSON-RPC request to the MCP server"""
        if not self.process or not self.process.stdin:
            raise Exception("Not connected to MCP server")
        
        request_str = json.dumps(request) + "\n"
        self.process.stdin.write(request_str.encode())
        await self.process.stdin.drain()
    
    async def _read_response(self) -> Dict[str, Any]:
        """Read a JSON-RPC response from the MCP server"""
        if not self.process or not self.process.stdout:
            raise Exception("Not connected to MCP server")
        
        line = await self.process.stdout.readline()
        if not line:
            raise Exception("MCP server closed connection")
        
        try:
            return json.loads(line.decode().strip())
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from MCP server: {line.decode()}")
            raise e
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on the MCP server"""
        if not self.connected:
            raise Exception("Not connected to MCP server")
        
        # Send tool call request
        request = {
            "jsonrpc": "2.0",
            "id": 3,  # Could be incremented
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        await self._send_request(request)
        response = await self._read_response()
        
        if response.get("error"):
            return {
                "success": False,
                "error": response["error"]["message"]
            }
        
        # Extract text content from MCP response
        result = response.get("result", {})
        content = result.get("content", [])
        
        if content and len(content) > 0 and content[0].get("type") == "text":
            return {
                "success": True,
                "result": content[0]["text"]
            }
        
        return {
            "success": False,
            "error": "No text content in response"
        }
    
    def get_tools_for_openai(self) -> List[Dict[str, Any]]:
        """Convert MCP tools to OpenAI function format"""
        openai_tools = []
        
        for tool in self.tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["inputSchema"]
                }
            }
            openai_tools.append(openai_tool)
        
        return openai_tools

class MCPAccountingAgent:
    """Enhanced AI Agent for accounting operations using proper MCP integration"""
    
    def __init__(self, openai_client: OpenAI):
        self.openai_client = openai_client
        self.mcp_client = MCPAccountingClient()
        
    def _get_system_message(self, company_id: str = None) -> Dict[str, str]:
        """Get system message based on context"""
        if company_id:
            return {
                "role": "system",
                "content": f"""You are an AI accounting assistant working with company ID: {company_id}

COMPANY CONTEXT: You are currently working with a specific company (ID: {company_id}).

CRITICAL INSTRUCTIONS:
- You do NOT need to search for companies or ask which company to use
- You should directly call the appropriate tools with company_id: '{company_id}'
- When user asks for categories, call list_categories with company_id: '{company_id}'
- When user asks for transactions, call search_transactions with company_id: '{company_id}'
- When user asks for financial summary, call get_financial_summary with company_id: '{company_id}'

COMPLEX PROMPT SUPPORT:
- Handle multi-step workflows (e.g., "create 5 transactions, then generate report")
- Break down complex requests into sequential tool calls
- Maintain context across multiple operations
- Provide detailed progress updates for complex operations

PAYEE CREATION PATTERNS:
- "add [Name]" = create_payee with name: "[Name]"
- "add [Name] as payee" = create_payee with name: "[Name]"
- "create payee [Name]" = create_payee with name: "[Name]"
- Always extract the name from the user's request and include it in the function call

EXAMPLES:
- User: "add Zero" → call create_payee with company_id: '{company_id}', name: "Zero"
- User: "add John Doe as payee" → call create_payee with company_id: '{company_id}', name: "John Doe"
- User: "create 3 expense transactions for office supplies, then show me spending summary" → 
  1. Call create_transaction for each expense
  2. Call get_financial_summary to show spending

TOOL USAGE:
- list_categories: Use this to show categories for the company
- search_transactions: Use this to find transactions for the company  
- get_financial_summary: Use this to get financial summaries for the company
- create_transaction: Use this to create new transactions for the company
- create_payee: ALWAYS include both company_id: '{company_id}' AND name: "[extracted_name]"
- bulk_create_transactions: Use for creating multiple transactions efficiently
- analyze_spending_patterns: Use for detailed spending analysis

Always include company_id: '{company_id}' in function calls that require it.

For complex prompts:
1. Break down the request into logical steps
2. Execute each step sequentially
3. Provide progress updates
4. Summarize results at the end

Provide clear, helpful responses about the company's accounting data."""
            }
        else:
            return {
                "role": "system", 
                "content": """You are an AI accounting assistant. You help users manage their accounting data including:
- Companies and their financial information
- Categories for organizing transactions (COGS, EXPENSE, INCOME types)
- Payees (vendors, customers, etc.)
- Transactions (income and expenses)
- Financial analysis and reporting

COMPLEX PROMPT SUPPORT:
- Handle multi-step workflows and complex requests
- Break down complex operations into sequential steps
- Provide detailed progress updates
- Maintain context across multiple operations

IMPORTANT WORKFLOW FOR COMPANY OPERATIONS:
1. If a user mentions a company name or wants to work with a specific company:
   - First use search_companies to find companies and get their IDs
   - Use the company_id from the search results for subsequent operations

2. If a user asks for categories, transactions, etc. without specifying a company:
   - First list all companies using search_companies
   - Then ask the user which company they want to work with, OR
   - If there's only one company, use that one automatically

TOOL USAGE GUIDELINES:
- Always provide company_id parameter for tools that require it
- search_companies: Use to find companies (no company_id needed)
- list_categories: ALWAYS requires company_id
- All other operations: Check if they need company_id first

Always be precise with financial data and provide clear, helpful responses."""
            }
    
    async def chat_stream(self, messages: List[Dict[str, Any]], company_id: str = None) -> AsyncGenerator[str, None]:
        """Stream chat responses with enhanced complex prompt support"""
        try:
            # Ensure MCP client is connected
            if not self.mcp_client.connected:
                await self.mcp_client.connect()
            
            # Get available tools in OpenAI format
            tools = self.mcp_client.get_tools_for_openai()
            
            # Prepare messages with system prompt
            system_message = self._get_system_message(company_id)
            full_messages = [system_message] + messages
            
            # Create OpenAI completion with tools
            stream = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=full_messages,
                tools=tools,
                tool_choice="auto",
                stream=True,
                temperature=0.1  # Lower temperature for more precise accounting operations
            )
            
            # Track tool calls for this turn
            tool_calls = []
            current_tool_call = None
            
            # Process the stream
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    # Regular content - stream it
                    yield chunk.choices[0].delta.content
                
                elif chunk.choices[0].delta.tool_calls:
                    # Tool call detected
                    for tool_call in chunk.choices[0].delta.tool_calls:
                        if tool_call.index is not None:
                            # New tool call starting
                            if current_tool_call:
                                tool_calls.append(current_tool_call)
                            
                            current_tool_call = {
                                "id": tool_call.id,
                                "function": {
                                    "name": tool_call.function.name if tool_call.function.name else "",
                                    "arguments": tool_call.function.arguments if tool_call.function.arguments else ""
                                }
                            }
                        else:
                            # Continuing previous tool call
                            if current_tool_call and tool_call.function:
                                if tool_call.function.name:
                                    current_tool_call["function"]["name"] += tool_call.function.name
                                if tool_call.function.arguments:
                                    current_tool_call["function"]["arguments"] += tool_call.function.arguments
            
            # Add the last tool call if exists
            if current_tool_call:
                tool_calls.append(current_tool_call)
            
            # Execute tool calls if any were made
            if tool_calls:
                yield "\n\n"
                async for result in self._execute_tools(tool_calls, company_id, messages):
                    yield result
                    
        except Exception as e:
            logger.error(f"Error in chat stream: {e}")
            yield f"\n\nError: {str(e)}"
    
    async def _execute_tools(self, tool_calls: List[Dict[str, Any]], company_id: str = None, messages: List[Dict[str, Any]] = None) -> AsyncGenerator[str, None]:
        """Execute tool calls with enhanced argument processing"""
        
        for tool_call in tool_calls:
            try:
                function_name = tool_call["function"]["name"]
                arguments_str = tool_call["function"]["arguments"]
                
                # Skip empty tool calls
                if not function_name or not function_name.strip():
                    continue
                
                # Parse arguments
                try:
                    arguments = json.loads(arguments_str) if arguments_str else {}
                except json.JSONDecodeError:
                    yield f"❌ Error: Invalid arguments for {function_name}\n"
                    continue
                
                # Enhanced argument processing
                arguments = self._enhance_arguments(function_name, arguments, company_id, messages)
                
                # Debug log the final arguments
                logger.info(f"Executing {function_name} with arguments: {arguments}")
                yield f"🔧 Executing {function_name}...\n"
                
                # Call the MCP tool
                result = await self.mcp_client.call_tool(function_name, arguments)
                
                if result["success"]:
                    yield f"✅ {result['result']}\n\n"
                else:
                    yield f"❌ Error in {function_name}: {result['error']}\n\n"
                    
            except Exception as e:
                logger.error(f"Error executing tool {tool_call}: {e}")
                yield f"❌ Error executing tool: {str(e)}\n\n"
    
    def _enhance_arguments(self, function_name: str, arguments: Dict[str, Any], company_id: str = None, messages: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Enhance arguments with automatic injection and extraction"""
        
        # Inject company_id if not provided and tool requires it
        if company_id:
            tools_requiring_company_id = [
                "list_categories", "get_company_overview", "search_transactions", 
                "get_financial_summary", "create_transaction", "list_payees",
                "get_payee", "search_payees_advanced", "download_payees",
                "bulk_delete_payees", "create_payee", "update_payee", "delete_payee",
                "bulk_create_payees", "list_transactions", "get_transaction",
                "search_transactions_advanced", "download_transactions",
                "update_transaction", "delete_transaction", "bulk_delete_transactions",
                "create_category", "update_category", "delete_category",
                "bulk_create_categories", "bulk_delete_categories"
            ]
            
            if function_name in tools_requiring_company_id:
                if "company_id" not in arguments or not arguments.get("company_id"):
                    arguments["company_id"] = company_id
                    logger.info(f"Injected company_id {company_id} into {function_name} arguments")
        
        # Special handling for create_payee - extract name from user message if missing
        if function_name == "create_payee" and ("name" not in arguments or not arguments.get("name")):
            if messages:
                last_user_message = None
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        last_user_message = msg.get("content", "").lower()
                        break
                
                if last_user_message:
                    import re
                    patterns = [
                        r"add\s+([^as]+?)\s+as\s+payee",  # "add Zero as payee"
                        r"add\s+(.+)",                    # "add Zero"
                        r"create\s+payee\s+(.+)",        # "create payee Zero"
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, last_user_message)
                        if match:
                            extracted_name = match.group(1).strip()
                            arguments["name"] = extracted_name
                            logger.info(f"Extracted payee name '{extracted_name}' from user message")
                            break
        
        return arguments
    
    async def initialize(self) -> bool:
        """Initialize the agent by connecting to MCP server"""
        try:
            success = await self.mcp_client.connect()
            if success:
                tools_count = len(self.mcp_client.tools)
                logger.info(f"MCP Accounting agent initialized with {tools_count} tools")
                return True
            else:
                logger.error("Failed to initialize MCP accounting agent")
                return False
        except Exception as e:
            logger.error(f"Error initializing MCP accounting agent: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup resources"""
        try:
            await self.mcp_client.disconnect()
            logger.info("MCP Accounting agent cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up MCP accounting agent: {e}")
