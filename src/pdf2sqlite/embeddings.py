import os
import re
import litellm
import numpy as np
from collections import Counter
from sklearn.cluster import KMeans
from typing import List, Dict, Tuple
from pypdf import PdfReader, PdfWriter

def process_pdf_for_semantic_search(
        toc_and_sections,
        cursor,
        pdf_id,
        model_name: str = "mistral/mistral-embed",
        n_clusters: int = 5
):
    """
    Process a PDF for semantic search capabilities

    Args:
        pdf_path: Path to the PDF file
        cursor: SQLite cursor
        db: SQLite database connection
        model_name: Embedding model to use (OpenAI, AWS Bedrock, HuggingFace)
        n_clusters: Number of clusters for topic extraction

    Returns:
        Dictionary with section embeddings and topics
    """

    if not toc_and_sections or not toc_and_sections['sections']:
        print("No sections extracted from the PDF. There might be something wrong with it.")
        return None

    print(f"Generating embeddings for {len(toc_and_sections['sections'])} sections")

    # Step 1: Prepare section texts for embedding
    section_texts = []
    section_info = []

    # Retrieve section IDs from database
    for section_id, section_data in toc_and_sections['sections'].items():
        title = section_data['title']
        cursor.execute("SELECT id FROM pdf_sections WHERE title = ? AND pdf_id = ?", [title, pdf_id])
        db_section_id_row = cursor.fetchone()

        if db_section_id_row:
            db_section_id = db_section_id_row[0]
            cleaned_text = clean_text(section_data['text'])

            if len(cleaned_text.strip()) > 50:
                section_texts.append(cleaned_text)
                section_info.append({
                    'db_id': db_section_id,
                    'section_id': section_id,
                    'title': title,
                    'text': cleaned_text
                })

    if not section_texts:
        print("No valid sections found for embedding.")
        return None

    print(f"Prepared {len(section_texts)} sections for embedding")

    # Step 2: Generate embeddings
    print(f"Setting up embedding model: {model_name}...")
    if not setup_embedding_client(model_name):
        print("Failed to setup embedding client. Exiting.")
        return None

    print(f"Generating embeddings using {model_name}...")
    embeddings = get_embeddings(section_texts, model_name)

    # Step 3: Store embeddings in database
    print("Storing embeddings in database...")
    for i, section in enumerate(section_info):
        store_section_embedding(cursor, section['db_id'], embeddings[i])

        # Extract and store keywords
        keywords = extract_keywords(section['text'])
        store_section_keywords(cursor, section['db_id'], keywords)

    # Step 4: Cluster sections for topic extraction
    print(f"Clustering sections using KMeans with {n_clusters} clusters...")
    cluster_labels, cluster_info = cluster_texts(embeddings, [s['text'] for s in section_info], n_clusters)

    # Step 6: Store topics and section-topic relationships
    print("Storing topics and section-topic relationships...")
    for cluster_id, info in cluster_info.items():
        topic_name = info.get('name', f"Topic {cluster_id}")
        topic_description = ", ".join(info.get('keywords', []))
        create_or_get_topic(cursor, cluster_id, name=topic_name, description=topic_description)

    for i, (label, section) in enumerate(zip(cluster_labels, section_info)):
        store_section_topic(cursor, section['db_id'], label)

# TODO this would be a natural place to return data about the dimension of the
# embedding vectors
def setup_embedding_client(model_name: str = "mistral/mistral-embed"):
    """
    Set up LiteLLM client for embeddings

    Args:
        model_name: Name of the embedding model to use
                   Options: "mistral/mistral-embed" (Mistral),
                           "text-embedding-ada-002" (OpenAI),
                           "bedrock/amazon.titan-embed-text-v1" (AWS Bedrock),
                           "huggingface/sentence-transformers/all-MiniLM-L6-v2"

    Returns:
        True if setup successful, False otherwise
    """

    try:
        # Test the embedding model with a simple query
        test_response = litellm.embedding(
            model=model_name,
            input=["test"]
        )

        if test_response and test_response.data:
            print(f"Successfully configured embedding model: {model_name}")
            return True
        else:
            print(f"Failed to configure embedding model: {model_name}")
            return False

    except Exception as e:
        print(f"Error setting up LiteLLM embedding client: {e}")
        print("Make sure you have the required API keys configured:")
        print("- For Mistral: Set MISTRAL_API_KEY environment variable")
        print("- For OpenAI: Set OPENAI_API_KEY environment variable")
        print("- For AWS Bedrock: Set AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)")
        print("- For Hugging Face: Set HUGGINGFACE_API_KEY environment variable")
        return False

def clean_text(text: str) -> str:
    """
    Clean and normalize text for embedding

    Args:
        text: Raw text to clean

    Returns:
        Cleaned and normalized text
    """
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove special characters but keep basic punctuation
    text = re.sub(r'[^\w\s\.\,\;\:\?\!]', '', text)
    return text.strip()

def get_embeddings(texts: List[str], model_name: str = "mistral/mistral-embed") -> List[np.ndarray]:
    """
    Get embeddings using LiteLLM (supports multiple providers)

    Args:
        texts: List of text strings to embed
        model_name: Name of the embedding model to use

    Returns:
        List of embedding vectors as numpy arrays
    """

    embeddings = []
    batch_size = 20  # Adjust based on API limits

    print(f"Generating embeddings for {len(texts)} texts using {model_name}")

    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        print(f"Processing batch {i // batch_size + 1}/{(len(texts) + batch_size - 1) // batch_size}")

        try:
            # Truncate texts if too long
            truncated_texts = []
            for text in batch_texts:
                if len(text) > 8000:  # Conservative limit
                    truncated_texts.append(text[:8000])
                else:
                    truncated_texts.append(text)

            # Get embeddings using LiteLLM
            response = litellm.embedding(
                model=model_name,
                input=truncated_texts
            )

            # Extract embeddings from response
            batch_embeddings = []
            for embedding_obj in response.data:
                embedding = np.array(embedding_obj.embedding, dtype=np.float32)
                batch_embeddings.append(embedding)

            embeddings.extend(batch_embeddings)

        except Exception as e:
            print(f"Error getting embeddings for batch {i // batch_size + 1}: {e}")
            os.exit(1)

    print(f"Generated {len(embeddings)} embeddings")
    return embeddings

def store_section_embedding(cursor, section_id, embedding):
    """Store embedding for a PDF section using sqlite-vec storage"""

    # Insert embedding into vec0 table and get the rowid
    cursor.execute("INSERT INTO section_embeddings_vec(embedding) VALUES (?)", [embedding.astype(np.float32)])
    vec_rowid = cursor.lastrowid

    # Store the mapping between section_id and vec table rowid
    cursor.execute(
        "INSERT OR REPLACE INTO section_vec_mapping (section_id, vec_rowid) VALUES (?, ?)",
        [section_id, vec_rowid]
    )
    return vec_rowid


def store_section_keywords(cursor, section_id, keywords):
    """Store keywords for a PDF section"""
    # Convert list to comma-separated string
    keywords_str = ",".join(keywords)

    # Check if keywords already exist
    cursor.execute("SELECT id FROM section_keywords WHERE section_id = ?", [section_id])
    existing_id = cursor.fetchone()

    if existing_id:
        # Update existing keywords
        cursor.execute(
            "UPDATE section_keywords SET keywords = ? WHERE section_id = ?",
            [keywords_str, section_id]
        )
        return existing_id[0]
    else:
        # Insert new keywords
        cursor.execute(
            "INSERT INTO section_keywords (section_id, keywords) VALUES (?, ?)",
            [section_id, keywords_str]
        )
        return cursor.lastrowid

def store_section_topic(cursor, section_id, topic_id, confidence=1.0):
    """Store topic/cluster assignment for a PDF section"""
    # Check if topic assignment already exists
    cursor.execute(
        "SELECT id FROM section_topics WHERE section_id = ? AND topic_id = ?",
        [section_id, topic_id]
    )
    existing_id = cursor.fetchone()

    if existing_id:
        # Update existing topic assignment
        cursor.execute(
            "UPDATE section_topics SET confidence = ? WHERE section_id = ? AND topic_id = ?",
            [confidence, section_id, topic_id]
        )
        return existing_id[0]
    else:
        # Insert new topic assignment
        cursor.execute(
            "INSERT INTO section_topics (section_id, topic_id, confidence) VALUES (?, ?, ?)",
            [section_id, topic_id, confidence]
        )
        return cursor.lastrowid

def cluster_texts(embeddings: List[np.ndarray], texts: List[str] = None, n_clusters: int = 5) -> Tuple[List[int], Dict]:
    """
    Cluster text embeddings and generate topic summaries

    Args:
        embeddings: List of embeddings
        texts: List of corresponding texts (for topic naming)
        n_clusters: Number of clusters to create

    Returns:
        Tuple of (cluster labels, cluster_info)
    """
    if not embeddings or len(embeddings) == 0:
        return [], {}

    # Convert to numpy array
    embeddings_array = np.array(embeddings)

    # Adjust clusters if needed
    n_samples = len(embeddings)
    actual_n_clusters = min(n_clusters, n_samples)

    if actual_n_clusters <= 1:
        # If only one cluster possible, assign all to cluster 0
        labels = np.zeros(n_samples, dtype=int)
        topic_name = "All Content" if texts else "Topic 0"
        return labels.tolist(), {0: {"size": n_samples, "name": topic_name}}

    # Perform clustering
    clustering = KMeans(n_clusters=actual_n_clusters, random_state=42, n_init=10)
    labels = clustering.fit_predict(embeddings_array)

    # Create cluster info
    cluster_info = {}
    for cluster_id in range(actual_n_clusters):
        cluster_indices = np.where(labels == cluster_id)[0]

        # Generate descriptive name if texts are provided
        if texts:
            cluster_texts = [texts[i] for i in cluster_indices]
            topic_name = generate_topic_name(cluster_texts)
        else:
            topic_name = f"Topic {cluster_id}"

        # Extract top keywords if texts are provided
        if texts:
            cluster_texts = [texts[i] for i in cluster_indices]
            combined_text = " ".join(cluster_texts)
            top_keywords = extract_keywords(combined_text, max_keywords=10)
        else:
            top_keywords = []

        cluster_info[int(cluster_id)] = {
            "size": len(cluster_indices),
            "name": topic_name,
            "keywords": top_keywords
        }

    return labels.tolist(), cluster_info

def generate_topic_name(texts: List[str]) -> str:
    """
    Generate a descriptive name for a topic based on common keywords

    Args:
        texts: List of text sections in this topic

    Returns:
        Descriptive topic name
    """
    # Combine all texts
    combined_text = " ".join(texts)

    # Extract keywords
    keywords = extract_keywords(combined_text, max_keywords=30)

    if not keywords:
        return "Miscellaneous"

    # Count keyword frequencies
    word_counts = Counter([w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', combined_text)])

    # Score keywords by frequency and position in keyword list
    scored_keywords = {}
    for i, kw in enumerate(keywords[:10]):  # Consider top 10 keywords
        score = word_counts.get(kw.lower(), 0) * (1.0 - (i * 0.1))  # Weight by position
        scored_keywords[kw] = score

    # Select top 2-3 keywords for the name
    top_keywords = sorted(scored_keywords.items(), key=lambda x: x[1], reverse=True)[:3]

    if not top_keywords:
        return "Miscellaneous"

    # Construct name based on number of good keywords found
    if len(top_keywords) >= 3 and top_keywords[2][1] > 0.5:
        return f"{top_keywords[0][0].title()} & {top_keywords[1][0].title()} - {top_keywords[2][0].title()}"
    elif len(top_keywords) >= 2 and top_keywords[1][1] > 0.5:
        return f"{top_keywords[0][0].title()} & {top_keywords[1][0].title()}"
    else:
        return f"{top_keywords[0][0].title()}"

def extract_keywords(text: str, max_keywords: int = 15) -> List[str]:
    """
    Extract important keywords from text

    Args:
        text: Input text to extract keywords from
        max_keywords: Maximum number of keywords to return

    Returns:
        List of extracted keywords
    """
    # Remove common stop words
    stop_words = {'the', 'and', 'to', 'of', 'a', 'in', 'for', 'is', 'on', 'that',
                  'by', 'this', 'with', 'are', 'be', 'as', 'at', 'from', 'has', 'have',
                  'was', 'were', 'which', 'or', 'an', 'not', 'they', 'their', 'but',
                  'can', 'been', 'will', 'would', 'should', 'could', 'may', 'it', 'its'}

    # Extract words
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    filtered_words = [word for word in words if word not in stop_words]

    # Count frequencies
    word_counts = Counter(filtered_words)

    # Return top keywords
    return [word for word, _ in word_counts.most_common(max_keywords)]

def create_or_get_topic(cursor, topic_id, name=None, description=None):
    """Create a new topic or get existing one"""
    # Check if topic already exists
    cursor.execute("SELECT id FROM topics WHERE id = ?", [topic_id])
    existing_id = cursor.fetchone()

    if existing_id:
        # Update existing topic if name or description provided
        if name or description:
            updates = []
            params = []

            if name:
                updates.append("name = ?")
                params.append(name)

            if description:
                updates.append("description = ?")
                params.append(description)

            if updates:
                params.append(topic_id)
                cursor.execute(
                    f"UPDATE topics SET {', '.join(updates)} WHERE id = ?",
                    params
                )

        return existing_id[0]
    else:
        # Insert new topic
        cursor.execute(
            "INSERT INTO topics (id, name, description) VALUES (?, ?, ?)",
            [topic_id, name or f"Topic {topic_id}", description or ""]
        )
        return cursor.lastrowid
