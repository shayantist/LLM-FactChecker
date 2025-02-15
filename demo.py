import streamlit as st
from dataclasses import dataclass
import sys
import os
from datetime import datetime
from urllib.parse import urlparse
import json

import dspy

# Add pipeline directory to path
sys.path.append('./pipeline_v2/')

import dotenv
dotenv.load_dotenv()

# Import base classes and utilities
from main import (
    Document, Citation, Answer, ClaimComponent, Claim,
    SearchProvider, VectorStore, ClaimExtractor, QuestionGenerator,
    AnswerSynthesizer, ClaimEvaluator, OverallStatementEvaluator
)

class StreamlitFactCheckPipeline:
    def __init__(
        self,
        model_name,
        embedding_model: str,
        search_provider=None,
        context=None,
        retriever_k: int = 10,
    ):
        # Initialize components
        self.claim_extractor = ClaimExtractor()
        self.question_generator = QuestionGenerator()
        self.retriever = VectorStore(
            model_name=embedding_model,
            use_bm25=True,
            bm25_weight=0.5
        )
        self.answer_synthesizer = AnswerSynthesizer()
        self.claim_evaluator = ClaimEvaluator()
        self.overall_evaluator = OverallStatementEvaluator()
        
        self.search_provider = search_provider
        self.retriever_k = retriever_k

        # Add context documents to vector DB
        if context:
            self.retriever.add_documents(
                [doc.content for doc in context],
                [doc.metadata for doc in context]
            )

        # Create Streamlit placeholders for live updates
        self.status_placeholder = st.empty()
        self.progress_bar = st.progress(0)
        self.results_container = st.container()

    def update_status(self, message, progress=None):
        """Update status message and progress bar"""
        self.status_placeholder.markdown(f"**Status:** {message}")
        if progress is not None:
            self.progress_bar.progress(progress)

    def fact_check(self, statement: str, web_search: bool = True):
        # Clear previous results
        self.results_container.empty()
        st.empty()
        
        # Reset containers
        with self.results_container:
            st.markdown("### Pipeline Progress")
            
            # Step 1: Extract Claims
            claims_container = st.expander("Step 1: Claim Extraction", expanded=True)
            with claims_container:
                self.update_status("Extracting claims...", 0.1)
                st.markdown("Analyzing statement to extract verifiable claims...")
                claims = self.claim_extractor(statement)
                
                st.markdown(f"**Extracted {len(claims)} claims:**")
                for i, claim in enumerate(claims, 1):
                    st.markdown(f"""
                    <p style='margin-left:20px; color: {COLORS['CLAIM']};'>
                    {i}. {claim.text}
                    </p>
                    """, unsafe_allow_html=True)

            # Step 2: Generate Questions
            questions_container = st.expander("Step 2: Question Generation", expanded=True)
            with questions_container:
                self.update_status("Generating questions...", 0.2)
                
                for i, claim in enumerate(claims, 1):
                    st.markdown(f"**Claim {i}: {claim.text}**")
                    components = self.question_generator(statement, claim)
                    claim.components = components
                    
                    for j, component in enumerate(components, 1):
                        st.markdown(f"""
                        <p style='margin-left:20px;'>
                        <span style='color: {COLORS['QUESTION']};'>Q{j}: {component.question}</span><br>
                        <span style='color: {COLORS['REASONING']};'>Search Queries: {component.search_queries}</span>
                        </p>
                        """, unsafe_allow_html=True)

            # Step 3: Search and Retrieve Evidence
            evidence_container = st.expander("Step 3: Evidence Collection", expanded=True)
            with evidence_container:
                self.update_status("Collecting evidence...", 0.4)
                
                for claim in claims:
                    st.markdown(f"**Processing Claim: {claim.text}**")
                    
                    for component in claim.components:
                        st.markdown(f"*Question: {component.question}*")
                        
                        relevant_docs = []
                        for query in component.search_queries:
                            if web_search and self.search_provider:
                                st.markdown(f"Searching web for: `{query}`")
                                search_results = self.search_provider.search(query)
                                
                                # Add search results to vector store
                                documents, metadata = [], []
                                for result in search_results:
                                    if result.excerpt:
                                        documents.append(result.excerpt)
                                        metadata.append({
                                            "title": result.title,
                                            "url": result.url,
                                            "source": result.source
                                        })
                                        st.markdown(f"""
                                        <p style='margin-left:20px; color: {COLORS['CITATION']};'>
                                        • {result.title} ({result.url})
                                        </p>
                                        """, unsafe_allow_html=True)
                                
                                self.retriever.add_documents(documents, metadata)
                            
                            # Retrieve relevant documents
                            docs = self.retriever.retrieve(query, k=self.retriever_k)
                            relevant_docs.extend(docs)
                            
                        # Synthesize answer
                        st.markdown("*Synthesizing answer...*")
                        answer = self.answer_synthesizer(component, relevant_docs)
                        component.answer = answer
                        
                        st.markdown(f"""
                        <p style='margin-left:20px;'>
                        <span style='color: {COLORS['ANSWER']};'>{answer.text}</span>
                        </p>
                        """, unsafe_allow_html=True)
                        
                        if answer.citations:
                            st.markdown("*Citations:*")
                            for i, citation in enumerate(answer.citations, 1):
                                if citation:
                                    st.markdown(f"""
                                    <p style='margin-left:40px; color: {COLORS['CITATION']};'>
                                    [{i}] {citation.snippet}<br>
                                    — {citation.source_title} ({citation.source_url})
                                    </p>
                                    """, unsafe_allow_html=True)

            # Step 4: Evaluate Claims
            evaluation_container = st.expander("Step 4: Claim Evaluation", expanded=True)
            with evaluation_container:
                self.update_status("Evaluating claims...", 0.8)
                
                for i, claim in enumerate(claims, 1):
                    st.markdown(f"**Evaluating Claim {i}: {claim.text}**")
                    verdict, confidence, reasoning = self.claim_evaluator(claim)
                    claim.verdict = verdict
                    claim.confidence = confidence
                    claim.reasoning = reasoning
                    
                    st.markdown(f"""
                    <p style='margin-left:20px;'>
                    <span style='color: {COLORS['VERDICT']};'>Verdict: {verdict}</span><br>
                    <span style='color: {COLORS['CONFIDENCE']};'>Confidence: {confidence}</span><br>
                    <span style='color: {COLORS['REASONING']};'>Reasoning: {reasoning}</span>
                    </p>
                    """, unsafe_allow_html=True)

            # Step 5: Overall Evaluation
            final_container = st.expander("Step 5: Final Verdict", expanded=True)
            with final_container:
                self.update_status("Determining final verdict...", 0.9)
                
                verdict, confidence, reasoning = self.overall_evaluator(statement, claims)
                
                st.markdown(f"""
                <h3>Final Verdict</h3>
                <p style='color: {COLORS['VERDICT']};'>Verdict: {verdict}</p>
                <p style='color: {COLORS['CONFIDENCE']};'>Confidence: {confidence}</p>
                <p style='color: {COLORS['REASONING']};'>Reasoning: {reasoning}</p>
                """, unsafe_allow_html=True)

            self.update_status("Fact-check complete!", 1.0)
            return verdict, confidence, reasoning, claims

# Colors for UI
COLORS = {
    'HEADER': "#1f77b4",
    'STATEMENT': "#ff7f0e", 
    'VERDICT': "#2ca02c",
    'CONFIDENCE': "#d62728",
    'REASONING': "#9467bd",
    'QUESTION': "#9467bd",
    'ANSWER': "#2ca02c",
    'CITATION': "#d62728",
    'CLAIM': "#1f77b4"
}

def initialize_lm(model_name, api_key):
    """Initialize language model based on selection."""
    if model_name == 'gemini-1.5-flash':
        return dspy.LM('gemini/gemini-1.5-flash', api_key=api_key)
    elif model_name.startswith('openrouter/'):
        return dspy.LM('openrouter/' + model_name.split('/')[-1], api_key=api_key)
    elif model_name.startswith('ollama/'):
        return dspy.LM('ollama_chat/' + model_name.split('/')[-1], api_base='http://localhost:11434', api_key='')
    else:
        raise ValueError(f"Unsupported model: {model_name}")

def main():
    st.set_page_config(page_title="LLM Fact-Checker Demo", layout="wide")
    
    # Title and description
    st.title("🔍 LLM Fact-Checker Demo")
    st.markdown("""
    Enter a statement to fact-check and configure the pipeline settings below.
    The system will break down the statement, search for evidence, and provide a detailed analysis.
    """)

    # Sidebar configuration
    st.sidebar.header("Pipeline Configuration")
    
    # Model selection or allow user to enter their own model
    model_name = st.sidebar.selectbox(
        "Select Language Model",
        [
            "gemini-1.5-flash",
            "openrouter/claude-3-sonnet",
            "ollama/deepseek-coder",
            "ollama/mistral",
            "CUSTOM"
        ]
    )
    st.write(f"NOTE: For now, only gemini-1.5-flash is offered free of charge without an API key. If you want to use other models, feel free to bring your own key (BYOK...?)!")
    if model_name == "CUSTOM":
        model_name = st.sidebar.text_input("Enter Custom Model in LiteLLM format (e.g. openai/gpt-4o)", value="")

    # API key input based on model
    api_key = None
    if model_name == 'gemini-1.5-flash':
        # api_key = st.sidebar.text_input("Enter Google API Key", type="password")
        api_key = os.getenv('GOOGLE_GEMINI_API_KEY')
    elif model_name.startswith('openrouter/'):
        api_key = st.sidebar.text_input("Enter OpenRouter API Key", type="password")

    # Search configuration
    use_web_search = st.sidebar.checkbox("Enable Web Search", value=True)
    if use_web_search:
        search_provider = st.sidebar.selectbox("Search Provider", ["duckduckgo", "serper"])
        if search_provider == "serper":
            # serper_api_key = st.sidebar.text_input("Enter Serper API Key", type="password")
            serper_api_key = os.getenv('SERPER_API_KEY')
        else:
            serper_api_key = None

    # Context document input
    use_context = st.sidebar.checkbox("Include Context Document", value=False)
    context_doc = None
    if use_context:
        context_text = st.sidebar.text_area("Enter Context Document")
        if context_text:
            context_doc = Document(
                content=context_text,
                metadata={"title": "User Provided Context", "url": ""}
            )

    # Main input area
    with st.form("fact_check_form"):
        statement = st.text_area("Enter statement to fact-check", height=100)
        # statement_date = st.date_input("Statement Date")
        # statement_originator = st.text_input("Statement Originator (e.g., source, speaker)")
        submitted = st.form_submit_button("Fact Check")

    if submitted:
        if not statement:
            st.error("Please enter a statement to fact-check.")
            return
        
        if model_name.startswith(('gemini', 'openrouter')) and not api_key:
            st.error("Please enter an API key for the selected model.")
            return

        if use_web_search and search_provider == "serper" and not serper_api_key:
            st.error("Please enter a Serper API key for web search.")
            return

        try:
            # Initialize components
            lm = initialize_lm(model_name, api_key)
            dspy.settings.configure(lm=lm)

            search_provider_instance = None
            if use_web_search:
                search_provider_instance = SearchProvider(
                    provider=search_provider,
                    api_key=serper_api_key
                )

            # Initialize pipeline with Streamlit-aware components
            pipeline = StreamlitFactCheckPipeline(
                model_name=lm,
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
                search_provider=search_provider_instance,
                context=[context_doc] if context_doc else None
            )

            # Format full statement with context
            full_statement = f"{statement}"
            
            # Run pipeline with live updates
            verdict, confidence, reasoning, claims = pipeline.fact_check(
                statement=full_statement,
                web_search=use_web_search
            )

        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()