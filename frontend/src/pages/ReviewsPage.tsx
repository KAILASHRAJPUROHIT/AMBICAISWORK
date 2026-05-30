import { useEffect, useState } from 'react';
import ReviewTable from '../components/ReviewTable';
import { mockReviews } from '../mockApi';
import { getOpenReviews } from '../api/client';
import type { ReviewItem } from '../mockApi';

const ReviewsPage = () => {
  const [reviews, setReviews] = useState<ReviewItem[]>(mockReviews);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const liveReviews = await getOpenReviews();
        const mappedReviews: ReviewItem[] = liveReviews.map((r: any) => ({
          id: r.review_id,
          date: r.created_at.split('T')[0],
          amount: 0,
          source: r.entity_type,
          reason: r.reason,
          status: r.status === 'OPEN' ? 'Pending' : 'Flagged'
        }));

        setReviews(mappedReviews);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch reviews:', err);
        setError('Using mock data: Backend API unreachable');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  return (
    <div className="reviews-page">
      <h1>Audit Reviews</h1>
      <p>Items flagged for human review according to AI safety rules.</p>
      
      {loading && <div className="loading-indicator">Loading live reviews...</div>}
      {error && <div className="error-message">{error}</div>}

      <ReviewTable items={reviews} />
    </div>
  );
};

export default ReviewsPage;
