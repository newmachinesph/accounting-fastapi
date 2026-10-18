"""
MCP Client for connecting to the accounting MCP server
"""

import asyncio
import json
import logging
import subprocess
import threading
import queue
import time
import uuid
import os
import sys
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class AccountingMCPClient:
    """Simple MCP client that communicates via JSON-RPC over subprocess"""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.available_tools: List[Dict[str, Any]] = []
        self._connected = False
        self.output_queue = queue.Queue()
        self.reader_thread = None
        
    async def connect(self):
        """Connect to the MCP server"""
        try:
            current_dir = os.getcwd()
            server_script = os.path.join(current_dir, "mcp_server", "server.py")
            
            if not os.path.exists(server_script):
                raise FileNotFoundError(f"Server script not found: {server_script}")
            
            env = os.environ.copy()
            env["API_BASE_URL"] = "http://localhost:8000"
            env["PYTHONPATH"] = current_dir
            
            # Start server process
            self.process = subprocess.Popen(
                [sys.executable, server_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1
            )
            
            # Start reader thread
            self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
            self.reader_thread.start()
            
            # Wait a moment for server to start
            await asyncio.sleep(0.5)
            
            # Initialize session
            init_result = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "accounting-mcp-client",
                    "version": "1.0.0"
                }
            })
            
            if not init_result or not init_result.get("result"):
                raise Exception("Failed to initialize MCP session")
            
            # Try to get tools from server first (proper MCP way)
            try:
                tools_result = await self._send_request("tools/list", {}, timeout=5)
                if tools_result and tools_result.get("result"):
                    tools = tools_result["result"].get("tools", [])
                    self.available_tools = tools
                    logger.info(f"Loaded {len(tools)} tools from MCP server via tools/list")
                else:
                    raise Exception("tools/list returned no result")
            except Exception as e:
                logger.warning(f"tools/list failed ({e}), using server tool registry as fallback")
                # Fallback: Use the known tool registry that matches the server exactly
                # This ensures we have access to all 36 tools even if tools/list has issues
                self.available_tools = self._get_server_tool_registry()
                logger.info(f"Using fallback tool registry with {len(self.available_tools)} tools")
            
            self._connected = True
            logger.info(f"Connected to MCP server with {len(self.available_tools)} tools")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            await self.disconnect()
            return False
    
    def _read_output(self):
        """Read output from server process in separate thread"""
        while self.process and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if line:
                    self.output_queue.put(('stdout', line.strip()))
                else:
                    break
            except Exception as e:
                self.output_queue.put(('error', str(e)))
                break
    
    async def _send_request(self, method: str, params: Dict[str, Any], timeout: int = 10) -> Optional[Dict[str, Any]]:
        """Send JSON-RPC request to server"""
        if not self.process:
            raise Exception("Not connected to server")
        
        request_id = str(uuid.uuid4())
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        # Send request
        request_json = json.dumps(request) + "\n"
        self.process.stdin.write(request_json)
        self.process.stdin.flush()
        
        # Wait for response with timeout
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                msg_type, content = self.output_queue.get(timeout=0.1)
                if msg_type == 'stdout':
                    try:
                        response = json.loads(content)
                        if response.get("id") == request_id:
                            return response
                    except json.JSONDecodeError:
                        continue
                elif msg_type == 'error':
                    logger.error(f"Server error: {content}")
                    return None
            except queue.Empty:
                continue
        
        logger.warning(f"Request {method} timed out after {timeout} seconds")
        return None
    
    
    async def disconnect(self):
        """Disconnect from the MCP server"""
        self._connected = False
        
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                self.process.kill()
            self.process = None
        
        self.available_tools = []
        logger.info("Disconnected from MCP server")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on the MCP server"""
        if not self._connected:
            raise Exception("Not connected to MCP server")
        
        try:
            result = await self._send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })
            
            if result and result.get("error"):
                return {
                    "success": False,
                    "error": result["error"]["message"],
                    "tool_name": tool_name,
                    "arguments": arguments
                }
            
            # Extract text content from result
            if result and result.get("result"):
                tool_result = result["result"]
                content = tool_result.get("content", [])
                
                if content and len(content) > 0:
                    text_content = content[0].get("text", "")
                    return {
                        "success": True,
                        "result": text_content,
                        "tool_name": tool_name,
                        "arguments": arguments
                    }
            
            return {
                "success": True,
                "result": "Tool executed successfully",
                "tool_name": tool_name,
                "arguments": arguments
            }
            
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "tool_name": tool_name,
                "arguments": arguments
            }
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools"""
        return self.available_tools
    
    def get_tools_for_openai(self) -> List[Dict[str, Any]]:
        """Convert MCP tools to OpenAI function format"""
        openai_tools = []
        
        for tool in self.available_tools:
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
    
    def _get_server_tool_registry(self) -> List[Dict[str, Any]]:
        """Fallback tool registry matching the server's exact implementation"""
        return [
            # Core business tools
            {"name": "search_companies", "description": "Search and list companies with optional filtering", "inputSchema": {"type": "object", "properties": {"name_contains": {"type": "string", "description": "Filter companies by name containing this text"}}, "additionalProperties": False}},
            {"name": "get_company_overview", "description": "Get complete overview of a company including categories, payees, and transaction summaries", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "ID of the company to get overview for"}}, "required": ["company_id"], "additionalProperties": False}},
            {"name": "search_transactions", "description": "Advanced transaction search with multiple filters and business analytics", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID to search transactions for"}, "category_name": {"type": "string", "description": "Filter by category name (will lookup category ID)"}, "payee_name": {"type": "string", "description": "Filter by payee name (will lookup payee ID)"}, "description_contains": {"type": "string", "description": "Filter by description containing text"}, "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)"}, "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)"}, "min_amount": {"type": "number", "description": "Minimum transaction amount"}, "max_amount": {"type": "number", "description": "Maximum transaction amount"}, "transaction_type": {"type": "string", "enum": ["spent", "received", "all"], "description": "Type of transactions to search"}, "limit": {"type": "integer", "description": "Maximum number of results", "default": 50}}, "required": ["company_id"], "additionalProperties": False}},
            {"name": "get_financial_summary", "description": "Get financial summary and insights for a company with spending by category", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID to get summary for"}, "date_from": {"type": "string", "description": "Start date for summary (YYYY-MM-DD)"}, "date_to": {"type": "string", "description": "End date for summary (YYYY-MM-DD)"}}, "required": ["company_id"], "additionalProperties": False}},
            {"name": "export_accounting_data", "description": "Export accounting data (categories, payees, or transactions) with filtering options", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID to export data for"}, "data_type": {"type": "string", "enum": ["categories", "payees", "transactions"], "description": "Type of data to export"}, "format": {"type": "string", "enum": ["json", "csv"], "description": "Export format", "default": "csv"}, "filters": {"type": "object", "description": "Optional filters specific to the data type", "additionalProperties": True}}, "required": ["company_id", "data_type"], "additionalProperties": False}},
            {"name": "bulk_create_transactions", "description": "Create multiple transactions at once for efficient data entry", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID to create transactions for"}, "transactions": {"type": "array", "description": "Array of transaction objects to create", "items": {"type": "object", "properties": {"payee_name": {"type": "string", "description": "Name of payee (will lookup or create)"}, "category_name": {"type": "string", "description": "Name of category (will lookup)"}, "transaction_date": {"type": "string", "description": "Transaction date (YYYY-MM-DD)"}, "description": {"type": "string", "description": "Transaction description"}, "spent": {"type": "number", "description": "Amount spent (for expenses)"}, "received": {"type": "number", "description": "Amount received (for income)"}}, "required": ["category_name", "transaction_date", "description"]}}}, "required": ["company_id", "transactions"], "additionalProperties": False}},
            {"name": "merge_payees", "description": "Merge duplicate payees by moving all transactions from source to target payee", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "source_payee_name": {"type": "string", "description": "Name of payee to merge from"}, "target_payee_name": {"type": "string", "description": "Name of payee to merge into"}}, "required": ["company_id", "source_payee_name", "target_payee_name"], "additionalProperties": False}},
            {"name": "analyze_spending_patterns", "description": "Analyze spending patterns and provide insights for a company", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID to analyze"}, "analysis_period": {"type": "string", "enum": ["last_30_days", "last_90_days", "year_to_date", "custom"], "description": "Period to analyze", "default": "last_90_days"}, "date_from": {"type": "string", "description": "Custom start date (YYYY-MM-DD) - required if analysis_period is 'custom'"}, "date_to": {"type": "string", "description": "Custom end date (YYYY-MM-DD) - required if analysis_period is 'custom'"}}, "required": ["company_id"], "additionalProperties": False}},
            
            # Categories CRUD tools
            {"name": "list_categories", "description": "List all categories for a company", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}}, "required": ["company_id"], "additionalProperties": False}},
            {"name": "get_category", "description": "Get a specific category by ID", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "category_id": {"type": "string", "description": "Category ID"}}, "required": ["company_id", "category_id"], "additionalProperties": False}},
            {"name": "search_categories_advanced", "description": "Advanced search for categories with multiple filters", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "name": {"type": "string", "description": "Exact name match"}, "name_contains": {"type": "string", "description": "Name contains text"}, "type": {"type": "string", "description": "Category type"}, "types": {"type": "array", "items": {"type": "string"}, "description": "Multiple category types"}, "parent_category_name": {"type": "string", "description": "Parent category name"}, "has_parent": {"type": "boolean", "description": "True for subcategories, False for root"}, "limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0}}, "required": ["company_id"], "additionalProperties": False}},
            {"name": "download_categories", "description": "Create download link for categories data", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "format": {"type": "string", "enum": ["json", "csv"], "default": "csv"}, "name_contains": {"type": "string", "description": "Filter by name containing text"}, "type": {"type": "string", "description": "Filter by category type"}}, "required": ["company_id"], "additionalProperties": False}},
            {"name": "create_category", "description": "Create a new category", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "name": {"type": "string", "description": "Category name"}, "type": {"type": "string", "description": "Category type (e.g., COGS, EXPENSE, INCOME)"}, "parent_category_name": {"type": "string", "description": "Parent category name (optional)"}}, "required": ["company_id", "name", "type"], "additionalProperties": False}},
            {"name": "update_category", "description": "Update an existing category", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "category_name": {"type": "string", "description": "Current category name"}, "new_name": {"type": "string", "description": "New category name"}, "new_type": {"type": "string", "description": "New category type"}, "new_parent_category_name": {"type": "string", "description": "New parent category name"}}, "required": ["company_id", "category_name"], "additionalProperties": False}},
            {"name": "delete_category", "description": "Delete a category", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "category_name": {"type": "string", "description": "Category name to delete"}}, "required": ["company_id", "category_name"], "additionalProperties": False}},
            {"name": "bulk_create_categories", "description": "Create multiple categories at once", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "categories": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "type": {"type": "string"}, "parent_category_name": {"type": "string"}}, "required": ["name", "type"]}}}, "required": ["company_id", "categories"], "additionalProperties": False}},
            {"name": "bulk_delete_categories", "description": "Delete multiple categories at once", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "category_names": {"type": "array", "items": {"type": "string"}, "description": "Array of category names to delete"}}, "required": ["company_id", "category_names"], "additionalProperties": False}},
            {"name": "update_category_parent", "description": "Change the parent category of a specific category", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "category_name": {"type": "string", "description": "Category name to update"}, "new_parent_category_name": {"type": "string", "description": "New parent category name (null for root)"}}, "required": ["company_id", "category_name"], "additionalProperties": False}},
            {"name": "update_category_type", "description": "Change the type of a category", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "category_name": {"type": "string", "description": "Category name to update"}, "new_type": {"type": "string", "description": "New category type (e.g., COGS, EXPENSE, INCOME)"}}, "required": ["company_id", "category_name", "new_type"], "additionalProperties": False}},
            
            # Payees CRUD tools
            {"name": "list_payees", "description": "List all payees for a company", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}}, "required": ["company_id"], "additionalProperties": False}},
            {"name": "get_payee", "description": "Get a specific payee by ID", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "payee_id": {"type": "string", "description": "Payee ID"}}, "required": ["company_id", "payee_id"], "additionalProperties": False}},
            {"name": "search_payees_advanced", "description": "Advanced search for payees with filters", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "name": {"type": "string", "description": "Exact name match"}, "name_contains": {"type": "string", "description": "Name contains text"}, "limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0}}, "required": ["company_id"], "additionalProperties": False}},
            {"name": "download_payees", "description": "Create download link for payees data", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "format": {"type": "string", "enum": ["json", "csv"], "default": "csv"}, "name_contains": {"type": "string", "description": "Filter by name containing text"}}, "required": ["company_id"], "additionalProperties": False}},
            {"name": "bulk_delete_payees", "description": "Delete multiple payees at once", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "payee_names": {"type": "array", "items": {"type": "string"}, "description": "Array of payee names to delete"}}, "required": ["company_id", "payee_names"], "additionalProperties": False}},
            {"name": "create_payee", "description": "Create a new payee", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "name": {"type": "string", "description": "Payee name"}}, "required": ["company_id", "name"], "additionalProperties": False}},
            {"name": "update_payee", "description": "Update an existing payee", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "current_name": {"type": "string", "description": "Current payee name"}, "new_name": {"type": "string", "description": "New payee name"}}, "required": ["company_id", "current_name", "new_name"], "additionalProperties": False}},
            {"name": "delete_payee", "description": "Delete a payee", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "payee_name": {"type": "string", "description": "Payee name to delete"}}, "required": ["company_id", "payee_name"], "additionalProperties": False}},
            {"name": "bulk_create_payees", "description": "Create multiple payees at once", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "payee_names": {"type": "array", "items": {"type": "string"}, "description": "Array of payee names to create"}}, "required": ["company_id", "payee_names"], "additionalProperties": False}},
            
            # Transactions CRUD tools
            {"name": "list_transactions", "description": "List all transactions for a company", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}}, "required": ["company_id"], "additionalProperties": False}},
            {"name": "get_transaction", "description": "Get a specific transaction by ID", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "transaction_id": {"type": "string", "description": "Transaction ID"}}, "required": ["company_id", "transaction_id"], "additionalProperties": False}},
            {"name": "search_transactions_advanced", "description": "Advanced search for transactions with all API filters", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "category_id": {"type": "string", "description": "Category ID (direct)"}, "payee_id": {"type": "string", "description": "Payee ID (direct)"}, "category_name": {"type": "string", "description": "Category name (will lookup ID)"}, "payee_name": {"type": "string", "description": "Payee name (will lookup ID)"}, "description_contains": {"type": "string", "description": "Description contains text"}, "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)"}, "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)"}, "min_amount": {"type": "number", "description": "Minimum amount"}, "max_amount": {"type": "number", "description": "Maximum amount"}, "transaction_type": {"type": "string", "enum": ["spent", "received", "all"]}, "limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0}}, "required": ["company_id"], "additionalProperties": False}},
            {"name": "download_transactions", "description": "Create download link for transactions data", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "format": {"type": "string", "enum": ["json", "csv"], "default": "csv"}, "category_name": {"type": "string", "description": "Filter by category name"}, "payee_name": {"type": "string", "description": "Filter by payee name"}, "description_contains": {"type": "string", "description": "Filter by description text"}, "date_from": {"type": "string", "description": "Start date filter"}, "date_to": {"type": "string", "description": "End date filter"}, "transaction_type": {"type": "string", "enum": ["spent", "received", "all"]}}, "required": ["company_id"], "additionalProperties": False}},
            {"name": "create_transaction", "description": "Create a single transaction", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "payee_name": {"type": "string", "description": "Payee name (will create if doesn't exist)"}, "category_name": {"type": "string", "description": "Category name"}, "transaction_date": {"type": "string", "description": "Transaction date (YYYY-MM-DD)"}, "description": {"type": "string", "description": "Transaction description"}, "spent": {"type": "number", "description": "Amount spent (for expenses)"}, "received": {"type": "number", "description": "Amount received (for income)"}}, "required": ["company_id", "category_name", "transaction_date", "description"], "additionalProperties": False}},
            {"name": "update_transaction", "description": "Update an existing transaction", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "transaction_id": {"type": "string", "description": "Transaction ID to update"}, "payee_name": {"type": "string", "description": "New payee name"}, "category_name": {"type": "string", "description": "New category name"}, "transaction_date": {"type": "string", "description": "New transaction date"}, "description": {"type": "string", "description": "New description"}, "spent": {"type": "number", "description": "New spent amount"}, "received": {"type": "number", "description": "New received amount"}}, "required": ["company_id", "transaction_id"], "additionalProperties": False}},
            {"name": "delete_transaction", "description": "Delete a transaction", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "transaction_id": {"type": "string", "description": "Transaction ID to delete"}}, "required": ["company_id", "transaction_id"], "additionalProperties": False}},
            {"name": "bulk_delete_transactions", "description": "Delete multiple transactions at once", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "string", "description": "Company ID"}, "transaction_ids": {"type": "array", "items": {"type": "string"}, "description": "Array of transaction IDs to delete"}}, "required": ["company_id", "transaction_ids"], "additionalProperties": False}}
        ]

# Global MCP client instance
mcp_client = AccountingMCPClient()
