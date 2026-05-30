import ReviewTable from '../components/ReviewTable';
import { mockReviews } from '../mockApi';

const ReviewsPage = () => {
  return (
    <div className="reviews-page">
      <h1>Audit Reviews</h1>
      <p>Items flagged for human review according to AI safety rules.</p>
      <ReviewTable items={mockReviews} />
    </div>
  );
};

export default ReviewsPage;
