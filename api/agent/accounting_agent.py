"""
AI Accounting Agent with OpenAI function calling and MCP tool integration
"""

import json
import logging
import asyncio
import subprocess
import os
from typing import Dict, List, Any, AsyncGenerator
from openai import OpenAI

# Import the working client
from .working_client import working_client

logger = logging.getLogger(__name__)

class AccountingAgent:
    """AI Agent for accounting operations using OpenAI + MCP tools"""
    
    def __init__(self, openai_client: OpenAI):
        self.openai_client = openai_client
        self.system_message = {
            "role": "system",
            "content": """You are an AI accounting assistant. You help users manage their accounting data including:
- Companies and their financial information
- Categories for organizing transactions (COGS, EXPENSE, INCOME types)
- Payees (vendors, customers, etc.)
- Transactions (income and expenses)
- Financial analysis and reporting

IMPORTANT WORKFLOW FOR COMPANY OPERATIONS:

1. If a user mentions a company name (like "Company_20250804_151750") or wants to work with a specific company:
   - First use search_companies to find companies and get their IDs
   - Use the company_id from the search results for subsequent operations

2. If a user asks for categories, transactions, etc. without specifying a company:
   - First list all companies using search_companies
   - Then ask the user which company they want to work with, OR
   - If there's only one company, use that one automatically

3. When users say "use company [name]", treat this as a request to:
   - Search for that company to get its ID
   - Then perform subsequent operations with that company_id

TOOL USAGE GUIDELINES:
- Always provide company_id parameter for tools that require it
- search_companies: Use to find companies (no company_id needed)
- list_categories: ALWAYS requires company_id
- All other operations: Check if they need company_id first

EXAMPLE FLOWS:
User: "List all categories"
1. Call search_companies to get available companies
2. If multiple companies, ask which one; if one company, use it
3. Call list_categories with the company_id

User: "use company Company_20250804_151750"  
1. Call search_companies to find this company and get its ID
2. Acknowledge that you'll now work with this company
3. User can then ask for categories, transactions, etc.

Always be precise with financial data and provide clear, helpful responses."""
        }
    
    async def chat_stream(self, messages: List[Dict[str, Any]], company_id: str = None) -> AsyncGenerator[str, None]:
        """
        Stream chat responses with tool execution
        """
        try:
            # Ensure working client is initialized
            if not working_client._connected:
                await working_client.connect()
            
            # Get available tools in OpenAI format
            tools = working_client.get_tools_for_openai()
            
            # Create context-aware system message
            system_message = self.system_message.copy()
            if company_id:
                # Override the system message with company-specific instructions
                system_message["content"] = f"""You are an AI accounting assistant working with company ID: {company_id}

COMPANY CONTEXT: You are currently working with a specific company (ID: {company_id}).

CRITICAL INSTRUCTIONS:
- You do NOT need to search for companies or ask which company to use
- You should directly call the appropriate tools with company_id: '{company_id}'
- When user asks for categories, call list_categories with company_id: '{company_id}'
- When user asks for transactions, call search_transactions with company_id: '{company_id}'
- When user asks for financial summary, call get_financial_summary with company_id: '{company_id}'

PAYEE CREATION PATTERNS:
- "add [Name]" = create_payee with name: "[Name]"
- "add [Name] as payee" = create_payee with name: "[Name]"
- "create payee [Name]" = create_payee with name: "[Name]"
- Always extract the name from the user's request and include it in the function call

EXAMPLES:
- User: "add Zero" → call create_payee with company_id: '{company_id}', name: "Zero"
- User: "add John Doe as payee" → call create_payee with company_id: '{company_id}', name: "John Doe"

TOOL USAGE:
- list_categories: Use this to show categories for the company
- search_transactions: Use this to find transactions for the company  
- get_financial_summary: Use this to get financial summaries for the company
- create_transaction: Use this to create new transactions for the company
- create_payee: ALWAYS include both company_id: '{company_id}' AND name: "[extracted_name]"

Always include company_id: '{company_id}' in function calls that require it.

Provide clear, helpful responses about the company's accounting data."""
            
            # Prepare messages with system prompt
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
        """Execute tool calls and stream results"""
        
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
                
                # Inject company_id if not provided and tool requires it
                if company_id:
                    # List of tools that require company_id
                    tools_requiring_company_id = [
                        "list_categories", "get_company_overview", "search_transactions", 
                        "get_financial_summary", "create_transaction", "list_payees",
                        "get_payee", "search_payees_advanced", "download_payees",
                        "bulk_delete_payees", "create_payee", "update_payee", "delete_payee",
                        "bulk_create_payees", "list_transactions", "get_transaction",
                        "search_transactions_advanced", "download_transactions",
                        "update_transaction", "delete_transaction", "bulk_delete_transactions"
                    ]
                    
                    if function_name in tools_requiring_company_id:
                        # Always set company_id, even if it exists but is empty
                        if "company_id" not in arguments or not arguments.get("company_id"):
                            arguments["company_id"] = company_id
                            logger.info(f"Injected company_id {company_id} into {function_name} arguments")
                
                # Special handling for create_payee - extract name from user message if missing
                if function_name == "create_payee" and ("name" not in arguments or not arguments.get("name")):
                    # Get the last user message to extract payee name
                    last_user_message = None
                    if messages:
                        for msg in reversed(messages):
                            if msg.get("role") == "user":
                                last_user_message = msg.get("content", "").lower()
                                break
                    
                    if last_user_message:
                        import re
                        # Extract name from patterns like "add Zero", "add Zero as payee", "create payee Zero"
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
                
                # Debug log the final arguments
                logger.info(f"Executing {function_name} with arguments: {arguments}")
                yield f"🔧 Executing {function_name}...\n"
                
                # Call the working client tool
                result = await working_client.call_tool(function_name, arguments)
                
                if result["success"]:
                    yield f"✅ {result['result']}\n\n"
                else:
                    yield f"❌ Error in {function_name}: {result['error']}\n\n"
                    
            except Exception as e:
                logger.error(f"Error executing tool {tool_call}: {e}")
                yield f"❌ Error executing tool: {str(e)}\n\n"
    
    async def initialize(self):
        """Initialize the agent by connecting to working client"""
        try:
            success = await working_client.connect()
            if success:
                tools_count = len(working_client.get_available_tools())
                logger.info(f"Accounting agent initialized with {tools_count} tools")
                return True
            else:
                logger.error("Failed to initialize accounting agent - working client connection failed")
                return False
        except Exception as e:
            logger.error(f"Error initializing accounting agent: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup resources"""
        try:
            await working_client.disconnect()
            logger.info("Accounting agent cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up accounting agent: {e}")
