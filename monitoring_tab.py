import gradio as gr
from pathlib import Path
import os
import sys

# Adjust path to import from parent directories
sys.path.append(str(Path(__file__).resolve().parents[1]))

from monitoring.agent import ContosoCareAgent
from utils import get_azure_monitoring_link

# Keep a single agent instance for the monitoring session
monitoring_agent = None

def get_monitoring_agent():
    """Initializes and returns the monitoring agent."""
    global monitoring_agent
    if monitoring_agent is None:
        print("Initializing monitoring agent...")
        monitoring_agent = ContosoCareAgent(
            endpoint=os.getenv("PROJECT_ENDPOINT"),
            model=os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o")
        )
    return monitoring_agent

def monitoring_chat_interface(message, history):
    """Chat function that uses the dedicated monitoring agent."""
    agent = get_monitoring_agent()
    
    print("Processing message with monitoring agent...")
    result = agent.process(message)
    
    response_message = result.get("message", "Sorry, I encountered an error.")
    tool_calls = result.get("actual_tool_calls", [])
    
    # Don't include tool debug info in the main response for cleaner UI
    return response_message

def handle_user_feedback(data: gr.LikeData):
    """Handle thumbs up/down feedback and emit to telemetry."""
    agent = get_monitoring_agent()
    
    # Map Gradio's liked boolean to our feedback symbols
    feedback_symbol = "+" if data.liked else "-"
    feedback_text = "positive" if data.liked else "negative"
    
    # Get the response text that was rated
    response_text = data.value if isinstance(data.value, str) else str(data.value)
    
    print(f"User feedback: {feedback_text} for response: {response_text[:50]}...")
    
    # Emit feedback to telemetry through the agent's span manager
    if hasattr(agent, 'span_manager'):
        agent.span_manager.emit_user_feedback(
            feedback_symbol=feedback_symbol,
            details=f"User rated response as {feedback_text}"
        )
        print(f"Feedback event emitted to telemetry: {feedback_symbol}")
    
    return None  # No UI update needed

def create_monitoring_tab():
    """Creates the Gradio UI for the live monitoring tab with feedback support."""
    with gr.Column():
        # Documentation in collapsible accordion
        with gr.Accordion("📚 Documentation - Live Monitoring & Continuous Evaluation", open=False):
            gr.Markdown("""
            ### 🎯 What is Continuous Evaluation?
            
            Continuous evaluation provides **near real-time observability** for your AI agent:
            - **Automatic quality assessment**: Evaluates agent responses for relevance, fluency, and coherence
            - **Safety monitoring**: Checks for harmful content, bias, and inappropriate responses
            - **Agent-specific metrics**: Tracks intent resolution, task adherence, and tool call accuracy
            - **Performance tracking**: Monitors token usage, latency, and success rates
            - **User feedback integration**: Captures and correlates user satisfaction signals
            
            ### 📊 Evaluation Metrics
            
            #### **Quality Evaluators** ✨
            - **Relevance**: Is the response relevant to the user's query?
            - **Coherence**: Is the response logically consistent and well-structured?
            - **Fluency**: Is the response grammatically correct and natural?
            - **Apology Tone**: Measures apologetic language levels (higher scores = less apologetic)
            
            #### **Safety Evaluators** 🛡️
            - **Hate & Unfairness**: Detects biased or discriminatory content
            - **Violence**: Identifies violent or aggressive language
            - **Self-Harm**: Flags content related to self-harm
            - **Indirect Attack**: Catches subtle manipulation attempts
            - **Code Vulnerability**: Identifies potentially unsafe code patterns
            
            #### **Agent Evaluators** 🤖
            - **Intent Resolution**: Did the agent correctly understand and address the user's intent?
            - **Task Adherence**: Did the agent follow its instructions and stay on task?
            - **Tool Call Accuracy**: Were the right tools called with correct parameters?
            
            ### ⚙️ Configuration Requirements
            
            To enable continuous evaluation, you need:
            
            1. **Azure AI Foundry Project** (not hub-based)
            2. **Application Insights Resource** connected to your project
            3. **Environment Variables** properly configured:
               - `APPLICATIONINSIGHTS_CONNECTION_STRING`
               - `PROJECT_ENDPOINT`
               - `OPENAI_AGENTS_ENDPOINT` and `OPENAI_AGENTS_API_KEY`
               - `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_PROJECT_NAME`
            
            ### 🔧 Setup Instructions
            
            Follow the [Azure AI Foundry documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/continuous-evaluation-agents) to:
            
            1. **Connect Application Insights**:
               - Navigate to your project in Azure AI Foundry
               - Select **Monitoring** → **Application Analytics**
               - Connect your Application Insights resource
            
            2. **Configure Evaluators**:
               - The agent automatically runs quality, safety, and agent-specific evaluators
               - Results are published to both Application Insights and Azure AI Studio
               - Evaluations run asynchronously to avoid impacting response time
            
            3. **View Results**:
               - **Azure AI Studio**: See aggregated metrics and trends
               - **Application Insights**: Query raw telemetry data
               - **KQL Dashboards**: Use provided queries for custom analysis
            
            ### 📈 How It Works
            
            1. **User Query**: You send a message to the agent
            2. **Agent Processing**: The agent processes and generates a response
            3. **Telemetry Capture**: OpenTelemetry captures spans, events, and metrics
            4. **Background Evaluation**: Evaluators run asynchronously after response is sent
            5. **Results Publishing**: Evaluation scores are sent to Application Insights
            6. **Dashboard Updates**: Azure AI Studio dashboards update with new data
            
            ### 💡 Best Practices
            
            - **Sampling**: Configure sampling rates to balance cost and coverage
            - **Alerting**: Set up alerts for low evaluation scores
            - **Review**: Regularly review evaluation results to identify patterns
            - **Iteration**: Use insights to improve prompts and agent behavior
            - **Privacy**: Be mindful of sensitive data in traces and evaluations
            
            ### 🔍 Debugging Tips
            
            - Check Application Insights connection: Look for `gen_ai.evaluation.result` events
            - Verify evaluator initialization: Check logs for "Azure AI Evaluation SDK initialized"
            - Monitor background threads: Evaluations run in separate threads to avoid blocking
            - Review token usage: High token counts may impact evaluation latency
            
            > **Note**: Evaluations run in the background and don't impact response time. Results typically appear in dashboards within 1-2 minutes.
            """)
        
        gr.Markdown(
            "Interact with the Foundry agent with full OpenTelemetry tracing and continuous evaluation enabled.\n"
            "All conversations are automatically evaluated and sent to Application Insights.\n"
            "**Use the 👍/👎 buttons to provide feedback on responses.**"
        )
        
        gr.Markdown(f"**[View Live Traces and Evaluations in Azure AI Studio]({get_azure_monitoring_link()})** | **[Configuration Guide: Continuous Evaluation Setup](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/continuous-evaluation-agents)**")

        with gr.Row():
            with gr.Column(scale=2):
                # Use Blocks to create a ChatInterface with like/dislike functionality
                with gr.Blocks():
                    chatbot = gr.Chatbot(
                        height=500,
                        placeholder="<strong>ContosoCare Warranty Assistant</strong><br>Ask me about your warranty claim",
                        show_copy_button=True
                    )
                    
                    # Attach the like event handler for thumbs up/down
                    chatbot.like(handle_user_feedback, None, None)
                    
                    msg = gr.Textbox(
                        placeholder="Type your warranty question here...",
                        label="Your Message",
                        lines=2
                    )
                    
                    with gr.Row():
                        submit = gr.Button("Send", variant="primary")
                        clear = gr.Button("Clear")
                    
                    # Example buttons
                    with gr.Row():
                        gr.Examples(
                            examples=[
                                ["My phone screen cracked when I dropped it yesterday. I have ContosoCare Premium."],
                                ["I accidentally spilled coffee on my laptop. Can you help with my warranty claim?"],
                                ["My device stopped working after a software update. Is this covered?"]
                            ],
                            inputs=msg,
                            label="Example Questions"
                        )
                    
                    # Set up the chat functionality
                    def user_message(message, history):
                        return "", history + [[message, None]]
                    
                    def bot_response(history):
                        user_msg = history[-1][0]
                        response = monitoring_chat_interface(user_msg, history[:-1])
                        history[-1][1] = response
                        return history
                    
                    msg.submit(user_message, [msg, chatbot], [msg, chatbot]).then(
                        bot_response, chatbot, chatbot
                    )
                    submit.click(user_message, [msg, chatbot], [msg, chatbot]).then(
                        bot_response, chatbot, chatbot
                    )
                    clear.click(lambda: None, None, chatbot, queue=False)
            
            with gr.Column(scale=1):
                gr.Markdown("### 📊 What's Being Tracked")
                gr.Markdown("""
                **Per Conversation:**
                - Response relevance score
                - Fluency & coherence ratings
                - Apology tone assessment
                - Safety check results
                - Intent resolution success
                - Tool call accuracy
                - Token usage metrics
                - Response latency
                - **User feedback (👍/👎)**
                
                **Aggregated Metrics:**
                - Average evaluation scores
                - Success/failure rates
                - Token consumption trends
                - **User satisfaction patterns**
                - Safety incident frequency
                - Apologetic language patterns
                
                **Feedback Integration:**
                - Your thumbs up/down ratings are captured
                - Feedback is correlated with evaluation scores
                - Helps identify quality patterns
                """)
                
        with gr.Accordion("📈 Expected Evaluation Results", open=False):
            gr.Markdown("""
            ### Typical Score Ranges
            
            **Quality Metrics** (1-5 scale):
            - Relevance: 4.5+ (responses should be highly relevant)
            - Coherence: 4.0+ (logical and well-structured)
            - Fluency: 4.5+ (natural language flow)
            - Apology Tone: 4.0+ (direct responses with minimal apologetic language)
            
            **Safety Metrics** (0-7 scale, lower is better):
            - All safety scores should be < 3 (low risk)
            - Scores > 5 indicate potential safety issues
            
            **Agent Metrics** (0-5 scale):
            - Intent Resolution: 4.0+ (correctly understands user needs)
            - Task Adherence: 4.5+ (follows instructions well)
            - Tool Call Accuracy: 4.0+ (uses tools correctly)
            
            ### Common Patterns
            
            - **Warranty questions**: High relevance and intent resolution
            - **Direct responses**: Higher apology tone scores (less apologetic)
            - **Complex scenarios**: May show lower coherence initially
            - **Tool usage**: Should maintain high accuracy for warranty decisions
            """)