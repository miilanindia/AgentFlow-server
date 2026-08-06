import asyncio
from typing import Optional, Dict, Any, List
from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from app.agent.state import AgentState
from app.agent.control import wait_for_approval, task_control
from app.browser.controller import browser_controller, browser_manager
from app.websocket.manager import ws_manager
from app.core.config import settings
import urllib.parse
from loguru import logger
import json
import re

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, groq_api_key=settings.GROQ_API_KEY)

# Sabhi login/bot-walled sites block hain (substring matching for all TLDs)
BLOCKED_DOMAINS = ["glassdoor", "linkedin", "indeed", "monster", "naukri", "shine"]

def _is_blocked(url: str) -> bool:
    return any(b in url for b in BLOCKED_DOMAINS)

@tool
async def search_internet(query: str) -> str:
    """Searches the open internet using DuckDuckGo with the EXACT user query."""
    logger.info(f"[TOOL CALL] search_internet called with query: '{query}'")
    try:
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        await asyncio.sleep(3)
        await browser_controller.goto(search_url)
        results = await browser_controller.get_search_results(max_results=settings.MAX_SEARCH_RESULTS)

        if not results:
            return f"No search results found for '{query}'. Try a different search term."

        filtered = [r for r in results if r.get("url") and not _is_blocked(r["url"])]

        if not filtered:
            return f"All top results require login or are blocked. Try another search query."

        formatted = "\n".join([f"- {r['title'].strip()} -> {r['url']}" for r in filtered])
        logger.info(f"[TOOL RESULT] Search successful. Found {len(filtered)} web results.")
        return (
            f"Search results for '{query}':\n{formatted}\n\n"
            f"INSTRUCTION: Call visit_webpage with ONE of the EXACT URLs listed above. "
            f"Do not invent URLs. If the first site doesn't have jobs or asks for login, visit the next URL."
        )
    except Exception as e:
        logger.error(f"[TOOL ERROR] search_internet failed: {e}")
        return f"ERROR: Search failed. Try a different query."

@tool
async def visit_webpage(url: str) -> str:
    """Visits a webpage URL to read its content and find job details and links."""
    logger.info(f"[TOOL CALL] visit_webpage called with url: '{url}'")
    if _is_blocked(url):
        return f"SKIPPED: '{url}' requires login. Try another URL."
    try:
        await asyncio.sleep(3)
        await browser_controller.goto(url)
        status = browser_controller.get_last_status()
        if status is not None and status >= 400:
            return f"ERROR: '{url}' returned HTTP {status} (broken/dead link). SKIP this URL and try the next one from search results."
        text = await browser_controller.get_page_text()
        logger.info(f"[TOOL RESULT] visit_webpage success. Extracted {len(text)} chars.")
        
        # CAPTCHA ya Security Block detection (Sign in/Log in buttons in header are allowed)
        lower_text = text.lower()[:1500]
        if "captcha" in lower_text or "cloudflare" in lower_text or "access denied" in lower_text or "403 forbidden" in lower_text:
            logger.warning(f"[TOOL WARNING] Page '{url}' is protected by CAPTCHA or security block.")
            return "This page is protected by CAPTCHA or security block. Try another URL from search results."
            
        return text[:settings.MAX_PAGE_TEXT_CHARS]
    except Exception as e:
        logger.error(f"[TOOL ERROR] visit_webpage failed: {e}")
        return f"ERROR: Could not open '{url}'."

tools = [search_internet, visit_webpage]
llm_with_tools = llm.bind_tools(tools)

def _trim_messages(messages):
    if len(messages) <= settings.MAX_HISTORY_MESSAGES + 2:
        return messages
    head = messages[:2]
    tail = messages[-settings.MAX_HISTORY_MESSAGES:]
    while tail and isinstance(tail[0], ToolMessage):
        tail = tail[1:]
    return head + tail

async def agent_node(state: AgentState):
    logger.info("======== AGENT NODE STARTED ========")
    task_id = state.get("task_id", "")
    if task_id:
        await task_control.check_paused(task_id)
        
    messages = state.get("messages", [])
    tool_call_count = state.get("tool_call_count", 0)
    logger.info(f"[GRAPH] Tool call iteration: {tool_call_count}/{settings.MAX_TOOL_ITERATIONS}")

    if not messages:
        logger.info(f"[GRAPH] Initializing new agent task for goal: '{state['goal']}'")
        sys_msg = SystemMessage(content=(
            "You are an Autonomous AI Job Researcher. Your goal is to find real, working job listings without getting blocked by login walls. "
            "1. Take the user's EXACT goal and build a DuckDuckGo search query. Prefer well-known open job boards/ATS platforms "
            "(e.g. site:greenhouse.io, site:lever.co, site:remoteok.com, site:wellfound.com, site:himalayas.app, site:weworkremotely.com) "
            "but you are NOT limited to only these — a plain open query (no site: filter) is also valid, especially if a site-restricted search returns few results. "
            "DO NOT modify the user's core intent (role, location, seniority). "
            "2. Pass the query to 'search_internet'. If results look thin or mostly blocked, call 'search_internet' again with a DIFFERENT, broader phrasing "
            "(drop the site: filter, add words like 'careers apply', or try a different job board) instead of giving up. "
            "3. Call 'visit_webpage' on the most relevant job listing URLs from the results. "
            "4. If a website asks for login, shows CAPTCHA, returns a broken/dead link (HTTP error), or fails to load, SKIP it immediately and visit the next URL. DO NOT GIVE UP. "
            "5. LINK EXTRACTION RULE (IMPORTANT): When a page lists MULTIPLE jobs, do NOT use the current page's own URL as the job link. "
            "Instead, look at the '--- AVAILABLE LINKS ON PAGE ---' section returned with the page text, and pick the specific href whose "
            "link text matches that job's title (the real apply/detail link). Only use the current page URL directly if that page itself IS a single job's description page. "
            "Never output a bare homepage, root careers listing, or root domain URL as a job's link. "
            "6. TARGET JOB LISTING COUNT: Visit multiple job URLs from search results to collect several matching job listings, not just one. "
            "7. Respond with ONLY a JSON array of objects with keys: 'title', 'company', 'location', 'salary', 'posted_date', 'link'. No extra conversational text or formatting. "
            "Extract 'salary' (e.g. '$120,000' or '₹15LPA' or 'Not disclosed') and 'posted_date' (e.g. '2 days ago' or 'Recently') if mentioned in the page text.\n"
            "CRITICAL BLOCKLIST RULE: NEVER visit indeed.com, linkedin.com, glassdoor.com, glassdoor.co.in, naukri.com, monster.com, or shine.com. They are strictly blocked and require login. If you see them in search results, skip them and do NOT call visit_webpage on them. Only visit open ATS portals, greenhouse.io, lever.co, remoteok.com, or wellfound.com.\n"
            "CRITICAL FOCUS RULE: You must ONLY visit or search for actual job postings, job boards, or career pages. "
            "NEVER search for company history, products, reviews, pricing, founders, or general platform support. "
            "NEVER visit generic platform help links or company homepages which do not list open jobs. "
            "If a webpage is not a job description or job board, skip it immediately, return to your search results, and try the next job URL."
        ))
        messages = [sys_msg, HumanMessage(content=state["goal"])]

    trimmed_messages = _trim_messages(messages)

    # HARD LOOP BREAKER: tool limit reached. Force LLM to compile final JSON list.
    if tool_call_count >= settings.MAX_TOOL_ITERATIONS:
        logger.info(f"[GRAPH] Tool limit ({settings.MAX_TOOL_ITERATIONS}) reached. Forcing LLM to compile final JSON...")
        forced_messages = trimmed_messages + [
            HumanMessage(content=(
                "You have reached the maximum allowed tool iterations. Do NOT call any tools. "
                "Review all search results and webpage texts from previous messages. "
                "Respond RIGHT NOW with ONLY a JSON array of objects with keys: 'title', 'company', 'location', 'salary', 'posted_date', 'link' for all matching jobs found so far. "
                "If no jobs were found, return an empty array []."
            ))
        ]
        try:
            response = await llm.ainvoke(forced_messages) # No tools bound!
            return {"messages": [response]}
        except Exception as e:
            logger.error(f"[GRAPH] Forced final response failed: {e}")
            return {"messages": [AIMessage(content="[]")]}

    try:
        response = await llm_with_tools.ainvoke(trimmed_messages)
        logger.info(f"[GRAPH] LLM response received. Content length: {len(response.content)}. Tool calls: {len(response.tool_calls)}")
        if response.tool_calls:
            for tc in response.tool_calls:
                logger.info(f"[GRAPH] LLM requested Tool: {tc['name']} with Args: {tc['args']}")
        return {"messages": [response]}
    except Exception as e:
        error_str = str(e)
        logger.warning(f"[GRAPH] LLM primary call failed: {e}. Attempting custom parser fallback...")
        
        # 1. Parse failed_generation function calls from Groq error string (e.g. <function=search_internet{"query": ...}</function>)
        match_fn = re.search(r'<function=([a-zA-Z_]+)\s*(\{.*?\})\s*</function>', error_str, re.DOTALL)
        if match_fn:
            tool_name = match_fn.group(1)
            tool_args_str = match_fn.group(2)
            try:
                tool_args = json.loads(tool_args_str)
                logger.info(f"[GRAPH] Custom parser recovered Tool: {tool_name} with Args: {tool_args}")
                ai_msg = AIMessage(content="", tool_calls=[{"name": tool_name, "args": tool_args, "id": "groq_recovered_id"}])
                return {"messages": [ai_msg]}
            except Exception as parse_err:
                logger.error(f"[GRAPH] Custom parser JSON load failed: {parse_err}")

        # 2. Fallback to URL extraction if previous message was ToolMessage
        if messages and isinstance(messages[-1], ToolMessage):
            last_tool_text = messages[-1].content
            match_url = re.search(r'(https?://[^\s>"]+)', last_tool_text)
            if match_url:
                url = match_url.group(1)
                logger.info(f"[GRAPH] Custom parser parsed Tool: visit_webpage with Args: {{'url': '{url}'}}")
                fallback_msg = AIMessage(
                    content="",
                    tool_calls=[{"name": "visit_webpage", "args": {"url": url}, "id": "fallback_call_1"}]
                )
                return {"messages": [fallback_msg]}

        # 3. If step 0 initial search call failed, construct default initial search tool call
        if tool_call_count == 0:
            query = f"{state['goal']} site:greenhouse.io OR site:lever.co OR site:remoteok.com"
            logger.info(f"[GRAPH] Initial step search recovery tool call: search_internet with query: '{query}'")
            recovery_msg = AIMessage(
                content="",
                tool_calls=[{"name": "search_internet", "args": {"query": query}, "id": "initial_search_id"}]
            )
            return {"messages": [recovery_msg]}
        
        logger.error("[GRAPH] Fallback failed. Returning empty list.")
        return {"messages": [AIMessage(content="[]")]}

ROOT_DOMAINS = ["greenhouse.io", "greenhouse.com", "lever.co", "remoteok.com", "remoteok.io", "duckduckgo.com", "google.com"]

def _sanitize_and_validate_jobs(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    valid_jobs = []
    if not isinstance(jobs, list):
        return valid_jobs

    for job in jobs:
        if not isinstance(job, dict):
            continue
            
        link = str(job.get("link", "")).strip()
        if not link or not link.startswith("http"):
            continue

        parsed = urllib.parse.urlparse(link)
        netloc = parsed.netloc.lower().replace("www.", "")
        clean_path = parsed.path.strip("/")

        # REJECT root domain URLs (e.g. https://greenhouse.io/ or https://remoteok.com/ without specific job path)
        if any(netloc == domain for domain in ROOT_DOMAINS) and not clean_path:
            logger.warning(f"[SANITY REJECT] Rejected root domain link: {link}")
            continue

        title = str(job.get("title", "Job Position")).strip()
        company = str(job.get("company", "Company")).strip()
        location = str(job.get("location", "Not specified")).strip()
        salary = str(job.get("salary", "Not disclosed")).strip()
        if not salary or salary.lower() in ["null", "none", "undefined"]:
            salary = "Not disclosed"

        posted_date = str(job.get("posted_date", "Recently")).strip()
        if not posted_date or posted_date.lower() in ["null", "none", "undefined"]:
            posted_date = "Recently"

        valid_jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "salary": salary,
            "posted_date": posted_date,
            "link": link
        })
    return valid_jobs

def _fallback_heuristic_extract(url: str, text: str) -> Optional[Dict[str, Any]]:
    """
    LAST-RESORT SAFETY NET HEURISTIC EXTRACTOR.
    Extracts title, company, location, salary, posted_date, and full job link.
    """
    if "ERROR" in text or "SKIPPED" in text or "protected by CAPTCHA" in text or len(text) < 100:
        return None

    # Validate that URL is a specific job page URL and NOT a search/listing page
    parsed = urllib.parse.urlparse(url)
    clean_path = parsed.path.strip("/").lower()
    path_parts = [p for p in clean_path.split("/") if p]
    
    if not path_parts:
        return None

    last_part = path_parts[-1]
    GENERIC_ROOT_PATHS = ["", "search", "html", "index.html", "jobs", "careers", "career",
                           "openings", "open-positions", "job-openings", "apply", "job-search", "all"]
    
    if last_part in GENERIC_ROOT_PATHS:
        logger.info(f"[HEURISTIC REJECT] Rejected search/listing page by path: {url}")
        return None

    # Reject if URL query parameters contain search terms
    query_str = parsed.query.lower()
    if query_str and any(q in query_str for q in ["term=", "q=", "query=", "search="]):
        logger.info(f"[HEURISTIC REJECT] Rejected search/listing page by query: {url}")
        return None

    company = "Career Portal"
    try:
        path_parts = [p for p in parsed.path.split("/") if p]
        if "lever.co" in parsed.netloc and path_parts:
            company = path_parts[0].capitalize()
        elif "greenhouse.io" in parsed.netloc and path_parts:
            company = path_parts[0].capitalize()
        elif parsed.netloc:
            company = parsed.netloc.replace("www.", "").split(".")[0].capitalize()
    except Exception:
        pass

    lines = [line.strip() for line in text.strip().split("\n") if line.strip() and len(line.strip()) > 3]
    if not lines:
        return None
        
    title = lines[0]
    if len(lines) > 1 and any(generic in title.lower() for generic in ["careers", "home", "jobs", "apply", "cookie", "skip", "search"]):
        title = lines[1]
        
    if len(title) > 100 or len(title) < 3 or any(w in title.lower() for w in ["cookie", "privacy", "copyright", "javascript"]):
        return None

    location = "Bengaluru, India"
    lower_text = text[:2000].lower()
    if "bengaluru" in lower_text or "bangalore" in lower_text:
        location = "Bengaluru, India"
    elif "remote" in lower_text:
        location = "Remote"
    elif "hybrid" in lower_text:
        location = "Bengaluru (Hybrid)"

    # Extract Salary using Regex
    salary = "Not disclosed"
    salary_match = re.search(r'(\$|₹|₹\s*\d|\bINR\b|\bUSD\b|\b\d+k\b|\b\d+\s*lpa\b|\d[\d,]*\s*-\s*[\d,]+)', text[:3000], re.IGNORECASE)
    if salary_match:
        for line in lines[:30]:
            if salary_match.group(0) in line and len(line) < 60:
                salary = line
                break
        if salary == "Not disclosed":
            salary = salary_match.group(0)

    # Extract Date Posted using Regex
    posted_date = "Recently"
    date_match = re.search(r'(\d+\s*(?:day|week|month|hour)s?\s*ago|posted\s*:\s*[^\n]+|date\s*:\s*[^\n]+|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2})', text[:3000], re.IGNORECASE)
    if date_match:
        posted_date = date_match.group(0).strip()

    return {
        "title": title,
        "company": company,
        "location": location,
        "salary": salary,
        "posted_date": posted_date,
        "link": url
    }

async def tool_node(state: AgentState):
    logger.info("======== TOOL NODE STARTED ========")
    task_id = state.get("task_id", "")
    if task_id:
        await task_control.check_paused(task_id)
        
    controller = await browser_manager.get_or_create(task_id) if task_id else browser_controller
    last_message = state["messages"][-1]
    tool_outputs = []
    
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        logger.info(f"[GRAPH] Executing Tool '{tool_name}' with args {tool_args}...")
        try:
            if tool_name == "search_internet":
                query = tool_args.get("query", "")
                search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
                await asyncio.sleep(2)
                await controller.goto(search_url)
                results = await controller.get_search_results(max_results=settings.MAX_SEARCH_RESULTS)
                filtered = [r for r in results if r.get("url") and not _is_blocked(r["url"])]

                if not filtered:
                    # Level-3: Smart Query Mutation. Sab results login-walled/empty nikle,
                    # toh site: restriction hata kar aur alag ATS boards try karke automatically dobara search karo.
                    broadened_query = re.sub(r'\s*site:\S+(\s+OR\s+site:\S+)*', '', query).strip()
                    broadened_query = f"{broadened_query} careers apply site:wellfound.com OR site:himalayas.app OR site:weworkremotely.com"
                    logger.info(f"[GRAPH] Level-3 Smart Query Mutation triggered. '{query}' had 0 usable results -> retrying with '{broadened_query}'")
                    search_url2 = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(broadened_query)}"
                    await asyncio.sleep(2)
                    await controller.goto(search_url2)
                    results2 = await controller.get_search_results(max_results=settings.MAX_SEARCH_RESULTS)
                    filtered = [r for r in results2 if r.get("url") and not _is_blocked(r["url"])]
                    query = broadened_query

                if filtered:
                    formatted = "\n".join([f"- {r['title'].strip()} -> {r['url']}" for r in filtered])
                    result = f"Search results for '{query}':\n{formatted}"
                else:
                    result = f"No usable results found for '{query}' even after broadening the search. Try a completely different query/job board."
            elif tool_name == "visit_webpage":
                target_url = tool_args.get("url", "")
                if _is_blocked(target_url):
                    result = f"SKIPPED: '{target_url}' requires login."
                else:
                    await asyncio.sleep(2)
                    await controller.goto(target_url)
                    status = controller.get_last_status()
                    if status is not None and status >= 400:
                        logger.warning(f"[TOOL WARNING] Page '{target_url}' returned HTTP {status} (dead/broken link).")
                        result = f"ERROR: '{target_url}' returned HTTP {status} (broken/dead link). SKIP this URL and try the next one from search results."
                    else:
                        text = await controller.get_page_text()
                        lower_text = text.lower()[:1500]
                        if "captcha" in lower_text or "cloudflare" in lower_text or "access denied" in lower_text or "403 forbidden" in lower_text:
                            logger.warning(f"[TOOL WARNING] Page '{target_url}' is protected by CAPTCHA or security block.")
                            result = "This page is protected by CAPTCHA or security block. Try another URL from search results."
                        else:
                            result = text[:settings.MAX_PAGE_TEXT_CHARS]
            else:
                logger.warning(f"[GRAPH] Unknown tool requested: '{tool_name}'")
                result = f"ERROR: Unknown tool."
            logger.info(f"[GRAPH] Tool '{tool_name}' execution completed. Output length: {len(str(result))}")
        except Exception as e:
            logger.error(f"[GRAPH] Tool '{tool_name}' crashed: {e}")
            result = f"ERROR: Tool crashed: {e}."
        tool_outputs.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
        
    return {
        "messages": tool_outputs,
        "tool_call_count": state.get("tool_call_count", 0) + 1
    }

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        if state.get("tool_call_count", 0) >= settings.MAX_TOOL_ITERATIONS:
            logger.info(f"[GRAPH] Max iterations ({settings.MAX_TOOL_ITERATIONS}) reached. Transitioning to extract.")
            return "extract"
        logger.info("[GRAPH] Transition: agent -> tools (Tool calls present)")
        return "tools"
    logger.info("[GRAPH] Transition: agent -> extract (No tool calls, final answer phase)")
    return "extract"

async def extract_node(state: AgentState):
    logger.info("======== EXTRACT NODE STARTED ========")
    last_message = state["messages"][-1]
    extracted_jobs = []
    
    try:
        content = last_message.content
        logger.info(f"[GRAPH] Raw content to extract from: {content[:300]}...")
        
        # 1. Primary Extraction: Regex match LLM JSON response
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            try:
                jobs = json.loads(match.group(0))
                sanitized = _sanitize_and_validate_jobs(jobs)
                if len(sanitized) > 0:
                    logger.info(f"[GRAPH] Extracted {len(sanitized)} valid jobs successfully from LLM JSON.")
                    return {"extracted_jobs": sanitized}
            except Exception as parse_err:
                logger.warning(f"[GRAPH] Regex matched JSON block but parsing failed: {parse_err}")
        
        # 2. Secondary Extraction: Single capped LLM recovery fallback (max 2000 chars)
        logger.warning("[GRAPH] Primary extraction returned 0 jobs or failed. Triggering LLM recovery fallback...")
        truncated_content = content[:settings.MAX_PAGE_TEXT_CHARS]
        fallback_prompt = (
            "You are a strict data formatter. Convert the following raw text containing job listings into a valid JSON array of job objects. "
            "Each object MUST have the keys: 'title', 'company', 'location', 'salary', 'posted_date', 'link'. "
            "CRITICAL LINK RULE: The 'link' MUST be the exact direct job posting details URL or apply URL. Never use generic root domain URLs like 'https://greenhouse.io/' or 'https://remoteok.com/'. "
            "Provide ONLY the raw JSON array inside square brackets. Do not write any conversational text, markdown blocks, or explanations.\n\n"
            f"Raw Text:\n{truncated_content}"
        )
        try:
            response = await llm.ainvoke([HumanMessage(content=fallback_prompt)])
            logger.info(f"[GRAPH] Fallback response received: {response.content[:300]}...")
            match_fallback = re.search(r'\[.*\]', response.content, re.DOTALL)
            if match_fallback:
                jobs = json.loads(match_fallback.group(0))
                sanitized = _sanitize_and_validate_jobs(jobs)
                if len(sanitized) > 0:
                    logger.info(f"[GRAPH] Fallback recovered {len(sanitized)} valid jobs successfully!")
                    return {"extracted_jobs": sanitized}
        except Exception as fallback_err:
            logger.error(f"[GRAPH] LLM recovery fallback failed: {fallback_err}")
            
        # 3. Tertiary Last-Resort Safety Net: Call heuristic fallback ONLY if LLM outputs 0 jobs
        logger.warning("[GRAPH] Primary and LLM fallback extractions failed. Invoking last-resort heuristic fallback...")
        for msg in state.get("messages", []):
            if isinstance(msg, ToolMessage) and msg.content:
                url_match = re.search(r'https?://[^\s>"]+', msg.content)
                url = url_match.group(0) if url_match else "https://careers.portal"
                auto_job = _fallback_heuristic_extract(url, msg.content)
                if auto_job and not any(j.get("link") == auto_job["link"] for j in extracted_jobs):
                    extracted_jobs.append(auto_job)
                    
        final_sanitized = _sanitize_and_validate_jobs(extracted_jobs)
        logger.info(f"[GRAPH] Final extracted jobs count: {len(final_sanitized)}")
        return {"extracted_jobs": final_sanitized}
    except Exception as e:
        logger.error(f"[GRAPH] Parsing extracted jobs failed: {e}")
        return {"extracted_jobs": []}

async def approval_node(state: AgentState):
    logger.info("======== APPROVAL NODE STARTED ========")
    task_id = state["task_id"]
    extracted = state.get("extracted_jobs", [])
    logger.info(f"[GRAPH] Pending approval for Task {task_id}. Extracted {len(extracted)} jobs.")
    await ws_manager.send_status_update(task_id, "pending_approval", "Waiting for User Approval")
    await ws_manager.send_timeline_event(task_id, "approval_required", {"message": "Please approve to finalize.", "jobs": extracted})
    
    logger.info(f"[GRAPH] Waiting for human interaction on Task {task_id}...")
    approved = await wait_for_approval(task_id)
    logger.info(f"[GRAPH] Human operator response for Task {task_id}: {'APPROVED' if approved else 'REJECTED'}")
    return {"needs_approval": True, "is_approved": approved}

def after_approval(state: AgentState):
    if state.get("error"): 
        logger.warning("[GRAPH] Transition: approve -> END (State contains errors)")
        return END
    if not state.get("is_approved"): 
        logger.info("[GRAPH] Transition: approve -> END (Operator rejected task)")
        return END
    logger.info("[GRAPH] Transition: approve -> finalize (Operator approved task)")
    return "finalize"

async def finalize_node(state: AgentState):
    logger.info("======== FINALIZE NODE STARTED ========")
    final_table = state.get("extracted_jobs", [])
    logger.info(f"[GRAPH] Finalizing task. Returning {len(final_table)} jobs in table.")
    return {"final_table": final_table}

workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)
workflow.add_node("extract", extract_node)
workflow.add_node("approve", approval_node)
workflow.add_node("finalize", finalize_node)

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "extract": "extract"})
workflow.add_edge("tools", "agent")
workflow.add_edge("extract", "approve")
workflow.add_conditional_edges("approve", after_approval, {"finalize": "finalize", END: END})
workflow.add_edge("finalize", END)

app_graph = workflow.compile()