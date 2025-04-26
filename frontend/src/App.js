import React, { useState } from "react";

function App() {
  const [topic, setTopic] = useState("");
  const [phone, setPhone] = useState("");
  const [status, setStatus] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus("Sending...");
    const resp = await fetch("http://localhost:8000/api/digest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, phone_number: phone })
    });
    const data = await resp.json();
    if (data.status === "digest_sent" || data.status === "received") {
      setStatus("Request received! You'll get a text soon.");
    } else {
      setStatus("Error. Try again.");
    }
  };

  return (
    <div className="app-container">
      <header>
        <div className="logo">
          <span className="logo-icon">📰</span>
          <h1>Cascade Digest</h1>
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
            <p>Get personalized news digests delivered straight to your phone. No more endless scrolling, just the news that matters to you.</p>
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
                  placeholder="E.g., Technology, Sports, Politics"
                  required
                />
              </div>
              
              <div className="input-group">
                <label htmlFor="phone">Phone Number</label>
                <input
                  id="phone"
                  type="tel"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  placeholder="+1 (555) 123-4567"
                  required
                />
                <small>We'll text your digest to this number</small>
              </div>
              
              <button type="submit" className="submit-button">
                Get My Digest <span className="arrow">→</span>
              </button>
            </form>
            
            <div className={`status-message ${status ? 'active' : ''}`}>
              {status}
            </div>
          </div>
        </section>

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
              <p>"Cascade Digest has completely changed how I consume news. No more information overload!"</p>
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
            <h2>Cascade Digest</h2>
          </div>
          <p>&copy; {new Date().getFullYear()} Cascade Digest. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}

export default App;