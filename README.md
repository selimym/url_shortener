# Functional Requirements


## Core Requirements

- **URL Shortening:** Users should be able to input a long URL and receive a unique, shortened alias. The shortened URL should use a compact format with English letters and digits to save space and ensure uniqueness.  
- **URL Redirection:** When users access a shortened URL, the service should redirect them seamlessly to the original URL with minimal delay.  
- **Link Analytics:** The system should be able to track the number of times each shortened URL is accessed to provide insights into link usage.

## Scale Requirements

- **100M Daily Active Users**  
- **Read:write ratio:** 100:1  
- **Write volume:** ~1 million write requests per day  
- **Entry size:** ~500 bytes per record


# Non-Functional Requirements

- **High Availability:** The service should ensure that all URLs are accessible 24/7, with minimal downtime, so users can reliably reach their destinations.  
- **Low Latency:** URL redirections should occur almost instantly (ideally under a few milliseconds) to provide a seamless experience.  
- **High Durability:** Shortened URLs should persist over time, even across server failures, ensuring long-term accessibility.  

