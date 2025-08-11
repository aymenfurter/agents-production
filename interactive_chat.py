import gradio as gr
import asyncio
import uuid
from pathlib import Path
import sys
import os

# Import agent classes using absolute imports
from variants.direct_inference.agent import DirectInferenceAgent as DirectAgent
from variants.foundry_agents.agent import ContosoCareAgent as FoundryAgent
from variants.openai_agents.agent import ContosoCareAgent as OpenAIAgent

agents = {}
# Track session overrides for cleared conversations
session_overrides = {}

def get_session_id(request: gr.Request = None):
    """Generate or retrieve session ID for the user."""
    if request and hasattr(request, 'session_hash'):
        base_session = f"session_{request.session_hash}"
        # Check if we have an override (from clearing history)
        return session_overrides.get(base_session, base_session)
    return f"session_{uuid.uuid4().hex[:8]}"

def get_agent(agent_choice, use_guardrails, session_id):
    """Initializes and returns the selected agent, caching for reuse per session."""
    key = (agent_choice, use_guardrails, session_id)
    if key not in agents:
        print(f"Initializing agent: {agent_choice} with guardrails: {use_guardrails} for session: {session_id}")
        if "Direct Inference" in agent_choice:
            agents[key] = DirectAgent(endpoint=os.getenv("AZURE_ML_ENDPOINT"), use_guardrails=use_guardrails)
        elif "Foundry" in agent_choice:
            model = "gpt-4.1" if "GPT-4.1" in agent_choice else "gpt-35-turbo"
            if use_guardrails:
                model = f"{model}-blocklist"
            agents[key] = FoundryAgent(endpoint=os.getenv("PROJECT_ENDPOINT"), model=model)
        elif "OpenAI Agents" in agent_choice:
            agents[key] = OpenAIAgent(model="gpt-5", session_id=session_id)
    return agents[key]

async def chat_interface(message, history, agent_choice, use_guardrails, request: gr.Request = None):
    """The main chat function that interacts with the selected agent."""
    session_id = get_session_id(request)
    agent = get_agent(agent_choice, use_guardrails, session_id)
    
    print(f"Processing message with {agent_choice} (session: {session_id})...")
    if "OpenAI Agents" in agent_choice:
        result = await agent.process(message)
    else:
        result = agent.process(message)
    
    response_message = result.get("message", "Sorry, I encountered an error.")
    tool_calls = result.get("actual_tool_calls", [])
    
    tool_log = "\n".join([f"[TOOL] {call['name']} | ARGS: {call['arguments']}" for call in tool_calls])
    full_response = f"{response_message}\n\n--- Debug: Tool Calls ---\n{tool_log}"
    
    return full_response

async def clear_conversation_history(agent_choice, use_guardrails, request: gr.Request = None):
    """Clear the conversation history for the current session by creating new agent instances."""
    if request and hasattr(request, 'session_hash'):
        base_session = f"session_{request.session_hash}"
        # Generate a new unique session ID
        new_session_id = f"session_{uuid.uuid4().hex[:8]}"
        # Store the override mapping
        session_overrides[base_session] = new_session_id
        current_session_id = new_session_id
    else:
        current_session_id = f"session_{uuid.uuid4().hex[:8]}"
    
    # Clean up old agents for all possible session IDs related to this user
    keys_to_remove = []
    for key in agents.keys():
        key_agent_choice, key_guardrails, key_session = key
        if (key_agent_choice == agent_choice and 
            key_guardrails == use_guardrails and 
            (key_session == base_session if request and hasattr(request, 'session_hash') else True)):
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        old_agent = agents[key]
        # Clean up the old agent if it has cleanup methods
        if hasattr(old_agent, '__del__'):
            try:
                old_agent.__del__()
            except:
                pass
        if hasattr(old_agent, 'close_session'):
            try:
                old_agent.close_session()
            except:
                pass
        # Remove from cache
        del agents[key]
    
    print(f"Conversation cleared! New session ID: {current_session_id}")
    
    if "OpenAI Agents" in agent_choice:
        return "Conversation history cleared! New agent instance created.", []
    elif "Foundry" in agent_choice:
        return "Conversation cleared! New thread created for fresh conversation.", []
    else:
        return "Conversation cleared! (Note: Full history clearing supported for OpenAI Agents and Foundry agents)", []

def create_interactive_chat_tab():
    """Creates the Gradio UI for the interactive chat tab."""
    with gr.Column():
        with gr.Row():
            agent_choice = gr.Dropdown(
                label="Select Agent Framework",
                choices=[
                    "Direct Inference (GPT-2)",
                    "Foundry (GPT-4.1)",
                    "Foundry (GPT-3.5)",
                    "OpenAI Agents (GPT-5)"
                ],
                value="Foundry (GPT-4.1)"
            )
            use_guardrails = gr.Checkbox(
                label="Enable Guardrails",
                value=True,
                info="Enable content safety guardrails for input and output filtering."
            )
        
        with gr.Row():
            clear_btn = gr.Button("Clear History", variant="secondary")

        chatbot = gr.Chatbot(height=650, type='messages')
        
        chat_ui = gr.ChatInterface(
            fn=chat_interface,
            chatbot=chatbot,
            additional_inputs=[agent_choice, use_guardrails],
            description="Ask a question about your warranty claim.",
            examples=[
                ["I dropped my phone and the screen is cracked. I have ContosoCare+."],
                ["My laptop won't turn on after I spilled coffee on it."],
                ["I was angry and threw my tablet against the wall."]
            ],
            fill_height=True
        )
        
        # Connect clear button to clear history function and reset chatbot
        clear_btn.click(
            fn=clear_conversation_history,
            inputs=[agent_choice, use_guardrails],
            outputs=[gr.Textbox(visible=False), chatbot]
        )