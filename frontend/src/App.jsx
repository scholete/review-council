import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ReviewInterface from './components/ReviewInterface';
import { api } from './api';
import './App.css';

function App() {
  const [reviews, setReviews] = useState([]);
  const [currentReviewId, setCurrentReviewId] = useState(null);
  const [currentReview, setCurrentReview] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    loadReviews();
  }, []);

  useEffect(() => {
    if (currentReviewId) {
      loadReview(currentReviewId);
    }
  }, [currentReviewId]);

  const loadReviews = async () => {
    try {
      const revs = await api.listReviews();
      setReviews(revs);
    } catch (e) {
      console.error('Failed to load reviews:', e);
    }
  };

  const loadReview = async (id) => {
    try {
      const rev = await api.getReview(id);
      setCurrentReview(rev);
    } catch (e) {
      console.error('Failed to load review:', e);
    }
  };

  const handleNewReview = () => {
    setCurrentReviewId(null);
    setCurrentReview(null);
  };

  const handleSelectReview = (id) => {
    setCurrentReviewId(id);
  };

  const handleSubmitDiff = async (diffText, repo, prTitle, prDescription) => {
    setIsLoading(true);
    const tempId = 'pending';
    const pendingReview = {
      id: tempId,
      status: 'in_progress',
      messages: [{
        role: 'assistant',
        stage1: null,
        stage2: null,
        stage3: null,
        metadata: null,
        loading: { stage1: false, stage2: false, stage3: false },
      }],
    };
    setCurrentReview(pendingReview);
    setCurrentReviewId(tempId);

    try {
      await api.submitDiffStream(diffText, repo, prTitle, prDescription, (eventType, event) => {
        setCurrentReview((prev) => {
          if (!prev || !prev.messages?.length) return prev;
          const messages = [...prev.messages];
          const lastMsg = { ...messages[messages.length - 1] };
          messages[messages.length - 1] = lastMsg;

          switch (eventType) {
            case 'review_created':
              setCurrentReviewId(event.review_id);
              return { ...prev, id: event.review_id };

            case 'stage1_start':
              lastMsg.loading = { ...lastMsg.loading, stage1: true };
              break;

            case 'stage1_complete':
              lastMsg.stage1 = event.data;
              lastMsg.loading = { ...lastMsg.loading, stage1: false };
              break;

            case 'stage2_start':
              lastMsg.loading = { ...lastMsg.loading, stage2: true };
              break;

            case 'stage2_complete':
              lastMsg.stage2 = event.data;
              lastMsg.metadata = event.metadata;
              lastMsg.loading = { ...lastMsg.loading, stage2: false };
              break;

            case 'stage3_start':
              lastMsg.loading = { ...lastMsg.loading, stage3: true };
              break;

            case 'stage3_complete':
              lastMsg.stage3 = event.data;
              lastMsg.loading = { ...lastMsg.loading, stage3: false };
              break;

            case 'complete':
              setIsLoading(false);
              loadReviews();
              return { ...prev, status: 'completed', messages };
          }
          return { ...prev, messages };
        });
      });
    } catch (e) {
      console.error('Review failed:', e);
      setIsLoading(false);
    }
  };

  const handleSubmitPr = async (prUrl) => {
    setIsLoading(true);
    try {
      const result = await api.submitPr(prUrl);
      setCurrentReviewId(result.review_id);
      setCurrentReview({
        id: result.review_id,
        status: 'completed',
        messages: [{
          role: 'assistant',
          stage1: result.stage1,
          stage2: result.stage2,
          stage3: result.stage3,
          metadata: result.metadata,
        }],
      });
      loadReviews();
    } catch (e) {
      console.error('PR review failed:', e);
    }
    setIsLoading(false);
  };

  return (
    <div className="app">
      <Sidebar
        reviews={reviews}
        currentReviewId={currentReviewId}
        onSelectReview={handleSelectReview}
        onNewReview={handleNewReview}
      />
      <ReviewInterface
        review={currentReview}
        onSubmitDiff={handleSubmitDiff}
        onSubmitPr={handleSubmitPr}
        isLoading={isLoading}
      />
    </div>
  );
}

export default App;
