import React, { useState, useEffect } from "react";
import DigestDisplay from "./DigestDisplay";

// News Anchor Loading Animation Component
function NewsAnchorLoading() {
  return (
    <div className="news-anchor-loading">
      <div className="news-desk"></div>
      <div className="news-anchor">
        <div className="head"></div>
        <div className="body"></div>
        <div className="microphone"></div>
      </div>
      <div className="loading-text">
        <span>Gathering News</span>
        <span className="dots">
          <span className="dot">.</span>
          <span className="dot">.</span>
          <span className="dot">.</span>
        </span>
      </div>
    </div>
  );
}

function App() {
  const [topic, setTopic] = useState("");
  const [status, setStatus] = useState("");
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const articlesPerPage = 6;
  const [aiDigest, setAiDigest] = useState(null);

  // No initial data loading on page load
  useEffect(() => {
    // Initialize the UI without pre-loading data
    setShowResults(false);
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus("Analyzing news sources...");
    setLoading(true);
    setAiDigest(null); // Reset AI digest
    
    try {
      // Set a timeout to handle network errors, much longer for AI processing
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 90000); // 90 seconds timeout for AI processing
      
      // Retry mechanism
      let retries = 2;
      let resp;
      
      while (retries >= 0) {
        try {
          resp = await fetch("http://localhost:8000/api/digest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
              topic,
              generate_ai_digest: true // Request AI digest
            }),
            signal: controller.signal
          });
          
          // If successful, break out of the retry loop
          if (resp.ok) break;
          
          // If not success but not a server error, also break (client errors shouldn't be retried)
          if (resp.status < 500) break;
          
          // Otherwise, retry server errors
          retries--;
          if (retries >= 0) {
            // Wait for 1 second before retrying
            await new Promise(resolve => setTimeout(resolve, 1000));
            console.log(`Retrying request, ${retries} retries left`);
          }
        } catch (e) {
          // Network error occurred, retry if we have retries left
          retries--;
          if (retries < 0) throw e; // re-throw if no more retries
          await new Promise(resolve => setTimeout(resolve, 1000));
          console.log(`Network error, retrying. ${retries} retries left`);
        }
      }
      
      clearTimeout(timeoutId);
      
      if (!resp.ok) {
        throw new Error(`HTTP error! Status: ${resp.status}`);
      }
      
      const data = await resp.json();
      
      if (data && (data.status === "digest_generated" || data.status === "digest_sent" || data.status === "received")) {
        setStatus("Digest generated successfully!");
        
        // Handle articles
        if (data.articles && Array.isArray(data.articles)) {
          setArticles(data.articles);
          setShowResults(true);
          setCurrentPage(1); // Reset to first page when searching new topic
        } else {
          console.error("Invalid articles format:", data.articles);
          setArticles([]);
          setShowResults(false);
        }
        
        // Handle AI digest if available
        if (data.ai_digest) {
          setAiDigest(data.ai_digest);
        } else if (data.digest) {
          // If no structured AI digest but there's a text digest, use that
          setAiDigest({ digest: data.digest });
        }
      } else {
        setStatus(data && data.error ? `Error: ${data.error}` : "Error. Try again.");
      }
    } catch (error) {
      console.error("Error submitting request:", error);
      
      // Provide more specific error messages
      if (error.name === 'AbortError') {
        setStatus("Request timed out. The server might be busy processing other requests. Please try again.");
      } else if (error.message.includes('NetworkError') || error.message.includes('Failed to fetch')) {
        setStatus("Network error. Please check your connection and try again.");
      } else if (error.message.includes('Status: 5')) {
        setStatus("Server error. Our team has been notified. Please try again in a few minutes.");
      } else {
        setStatus("Error processing your request. Please try again.");
      }
      
      setShowResults(false);
    } finally {
      setLoading(false);
    }
  };
  
  // Get current articles for pagination
  const indexOfLastArticle = currentPage * articlesPerPage;
  const indexOfFirstArticle = indexOfLastArticle - articlesPerPage;
  const currentArticles = articles && articles.length > 0 ? articles.slice(indexOfFirstArticle, indexOfLastArticle) : [];
  const totalPages = articles && articles.length > 0 ? Math.ceil(articles.length / articlesPerPage) : 0;

  // Change page
  const paginate = (pageNumber) => setCurrentPage(pageNumber);
  
  // Go to previous page
  const goToPreviousPage = () => {
    if (currentPage > 1) {
      setCurrentPage(currentPage - 1);
    }
  };
  
  // Go to next page
  const goToNextPage = () => {
    if (currentPage < totalPages) {
      setCurrentPage(currentPage + 1);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return "";
    
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString("en-US", {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch (e) {
      return "";
    }
  };
  
  const formatTimeAgo = (dateString) => {
    if (!dateString) return "";
    
    try {
      const publishedDate = new Date(dateString);
      const now = new Date();
      
      // Calculate time difference in milliseconds
      const timeDiff = now - publishedDate;
      
      // Convert to hours
      const hoursDiff = Math.floor(timeDiff / (1000 * 60 * 60));
      
      if (hoursDiff < 1) {
        // Less than an hour ago
        const minutesDiff = Math.floor(timeDiff / (1000 * 60));
        return `${minutesDiff} minute${minutesDiff !== 1 ? 's' : ''} ago`;
      } else if (hoursDiff < 24) {
        // Less than a day ago
        return `${hoursDiff} hour${hoursDiff !== 1 ? 's' : ''} ago`;
      } else if (hoursDiff < 48) {
        // Less than 2 days ago
        return 'Yesterday';
      } else {
        // More than 2 days ago - return formatted date
        const daysDiff = Math.floor(hoursDiff / 24);
        if (daysDiff < 7) {
          return `${daysDiff} day${daysDiff !== 1 ? 's' : ''} ago`;
        } else {
          return formatDate(dateString);
        }
      }
    } catch (e) {
      console.error("Error formatting time ago:", e);
      return "";
    }
  };

  return (
    <div className="app-container">
      <header>
        <div className="logo">
          <span className="logo-icon">📰</span>
          <h1>M.A.D</h1>
        </div>
        <nav>
          <ul>
            <li><a href="#">Home</a></li>
            <li><a href="#">Features</a></li>
            <li><a href="#">Pricing</a></li>
            <li><a href="#">About</a></li>
          </ul>
        </nav>
      </header>

      <main>
        <section className="hero">
          <div className="hero-content">
            <h2>Stay Informed, <span className="highlight">Effortlessly</span></h2>
            <p>Get personalized news digests on any topic delivered straight to your phone. Enter a topic below to see relevant articles and summaries.</p>
          </div>

          <div className="form-container">
            <div className="form-header">
              <h3>Get Your Daily Digest</h3>
              <p>Curated news on your topic of interest, delivered daily.</p>
            </div>

            <form onSubmit={handleSubmit}>
              <div className="input-group">
                <label htmlFor="topic">Topic of Interest</label>
                <input
                  id="topic"
                  type="text"
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                  placeholder="E.g., Technology, Ukraine, Climate Change, AI"
                  required
                />
              </div>
              
              
              <button type="submit" className="submit-button" disabled={loading}>
                {!loading ? "Get My Digest" : "Processing"} {!loading && <span className="arrow">→</span>}
              </button>
            </form>
            
            <div className={`status-message ${status ? 'active' : ''}`}>
              {status}
            </div>
          </div>
        </section>

        {loading ? (
          <section className="results-section">
            <NewsAnchorLoading />
          </section>
        ) : (
          showResults && (
            <section className="results-section">
              {/* AI Digest Display */}
              {aiDigest && <DigestDisplay aiDigest={aiDigest} />}
              
              {/* Articles Display */}
              {articles.length > 0 && (
              <>
                <h2>Top News Articles</h2>
                <div className="results-info">
                  <p>Found {articles.length} articles. Showing page {currentPage} of {totalPages}.</p>
                </div>
                <div className="results-container">
                  {currentArticles && currentArticles.length > 0 ? (
                    currentArticles.map((article, index) => (
                      <div className="article-card" key={index}>
                        <h3>
                          <a href={article.link} target="_blank" rel="noopener noreferrer">
                            {article.title || "No Title Available"}
                          </a>
                        </h3>
                        <div className="article-meta">
                          {article.source && <span className="article-source">{article.source}</span>}
                          {article.published && (
                            <span className="article-date" title={formatDate(article.published)}>
                              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="clock-icon">
                                <circle cx="12" cy="12" r="10" />
                                <polyline points="12 6 12 12 16 14" />
                              </svg>
                              {formatTimeAgo(article.published)}
                            </span>
                          )}
                        </div>
                        <p className="article-snippet">{article.snippet || "No preview available"}</p>
                        <a href={article.link} className="read-more" target="_blank" rel="noopener noreferrer">
                          Read full article
                        </a>
                      </div>
                    ))
                  ) : (
                    <div className="no-results">Loading articles...</div>
                  )}
                </div>
                
                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="pagination">
                    <button 
                      onClick={goToPreviousPage} 
                      disabled={currentPage === 1}
                      className={`pagination-button ${currentPage === 1 ? 'disabled' : ''}`}
                    >
                      Previous
                    </button>
                    
                    <div className="pagination-numbers">
                      {[...Array(totalPages).keys()].map(number => (
                        <button
                          key={number + 1}
                          onClick={() => paginate(number + 1)}
                          className={`pagination-number ${currentPage === number + 1 ? 'active' : ''}`}
                        >
                          {number + 1}
                        </button>
                      ))}
                    </div>
                    
                    <button 
                      onClick={goToNextPage} 
                      disabled={currentPage === totalPages}
                      className={`pagination-button ${currentPage === totalPages ? 'disabled' : ''}`}
                    >
                      Next
                    </button>
                  </div>
                )}
              </>
            )}
            </section>
          )
        )}

        <section className="features">
          <div className="feature">
            <div className="feature-icon">🔍</div>
            <h3>Smart Curation</h3>
            <p>Our AI analyzes thousands of sources to find the most relevant content for you.</p>
          </div>
          
          <div className="feature">
            <div className="feature-icon">⚡</div>
            <h3>Daily Updates</h3>
            <p>Get fresh content delivered every morning at your preferred time.</p>
          </div>
          
          <div className="feature">
            <div className="feature-icon">🔒</div>
            <h3>Private & Secure</h3>
            <p>We never share your personal information with third parties.</p>
          </div>
        </section>

        <section className="testimonials">
          <h2>What Our Users Say</h2>
          <div className="testimonial-container">
            <div className="testimonial">
              <p>"M.A.D has completely changed how I consume news. No more information overload!"</p>
              <div className="testimonial-author">— Sarah K., Journalist</div>
            </div>
            <div className="testimonial">
              <p>"I love getting my tech digest every morning. It's become an essential part of my day."</p>
              <div className="testimonial-author">— Michael T., Software Engineer</div>
            </div>
          </div>
        </section>
      </main>

      <footer>
        <div className="footer-content">
          <div className="footer-logo">
            <span className="logo-icon">📰</span>
            <h2>M.A.D</h2>
          </div>
          <p>&copy; {new Date().getFullYear()} M.A.D. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}

export default App;