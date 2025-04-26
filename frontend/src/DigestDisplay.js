import React from 'react';
import ReactMarkdown from 'react-markdown';

function DigestDisplay({ aiDigest }) {
  if (!aiDigest) return null;

  // Helper function to convert new lines to JSX breaks
  const formatText = (text) => {
    if (!text) return '';
    return text.split('\n').map((line, index) => (
      <React.Fragment key={index}>
        {line}
        <br />
      </React.Fragment>
    ));
  };
  
  // Format time ago from date string
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
          return new Date(dateString).toLocaleDateString("en-US", {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
          });
        }
      }
    } catch (e) {
      console.error("Error formatting time ago:", e);
      return "";
    }
  };

  // Style based on what data is available
  const isStructured = aiDigest.overall_summary || aiDigest.article_highlights;
  
  // Function to enhance article highlights with time stamps
  const enhanceMarkdownWithTimeAgo = (markdown) => {
    if (!markdown) return markdown;
    
    // Look for "**Published:**" patterns and add time ago if there's a date
    // This regex handles various date formats including ISO dates and formatted dates like "Apr 3, 2025+06:00"
    return markdown.replace(
      /\*\*Published:\*\* ([\d\-T:.Z+]+|[A-Za-z]+ \d+, \d{4}(?:[+-]\d{2}:\d{2})?)/g, 
      (match, dateStr) => {
        try {
          // Clean up the date string if it has timezone offsets like +06:00
          let cleanDateStr = dateStr;
          
          // Try to determine if this is an ISO date or a formatted date
          const isFormattedDate = /[A-Za-z]+ \d+, \d{4}/.test(dateStr);
          
          if (isFormattedDate) {
            // For formatted dates like "Apr 3, 2025+06:00", we just show "Apr 3, 2025"
            cleanDateStr = dateStr.replace(/([A-Za-z]+ \d+, \d{4})(?:[+-]\d{2}:\d{2})?/, "$1");
            return `**Published:** ${cleanDateStr}`;
          } else {
            // For ISO dates, calculate time ago
            const timeAgo = formatTimeAgo(cleanDateStr);
            if (timeAgo) {
              return `**Published:** ${timeAgo}`;
            }
          }
        } catch (e) {
          console.error("Error processing date:", e);
        }
        return match;
      }
    );
  };
  
  // Enhance article highlights if available
  const enhancedHighlights = enhanceMarkdownWithTimeAgo(aiDigest.article_highlights);
  
  return (
    <div className="digest-container">
      <h2>AI-Generated News Summary</h2>
      
      {isStructured ? (
        <>
          {aiDigest.overall_summary && (
            <div className="digest-summary">
              <h3>Latest Developments</h3>
              <p>{aiDigest.overall_summary}</p>
            </div>
          )}
          
          {enhancedHighlights && (
            <div className="article-highlights">
              <h3>Top Articles</h3>
              <div className="formatted-highlights">
                <ReactMarkdown 
                  components={{
                    a: ({node, ...props}) => (
                      <a 
                        {...props} 
                        target="_blank" 
                        rel="noopener noreferrer"
                      />
                    )
                  }}
                >
                  {enhancedHighlights}
                </ReactMarkdown>
              </div>
            </div>
          )}
        </>
      ) : (
        // Simple version with just the digest text
        <div className="digest-content">
          <div className="formatted-digest">
            {aiDigest.digest ? (
              <ReactMarkdown
                components={{
                  a: ({node, ...props}) => (
                    <a 
                      {...props} 
                      target="_blank" 
                      rel="noopener noreferrer"
                    />
                  )
                }}
              >
                {aiDigest.digest}
              </ReactMarkdown>
            ) : (
              formatText(aiDigest.digest || "No digest available")
            )}
          </div>
        </div>
      )}
      
      <div className="digest-footer">
        <p>Powered by M.A.D</p>
      </div>
    </div>
  );
}

export default DigestDisplay;