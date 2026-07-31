/**
 * NexRoute - Intelligent Scoring Engine
 * Evaluates provider metrics (price, latency, reputation) against optimization profiles.
 */

const WEIGHT_PROFILES = {
  cheapest: { price: 0.7, speed: 0.1, reputation: 0.2 },
  fastest:  { price: 0.1, speed: 0.7, reputation: 0.2 },
  balanced: { price: 0.34, speed: 0.33, reputation: 0.33 }
};

/**
 * Calculates raw score for a single provider based on weights.
 * Normalizes term magnitudes so price, speed, and reputation terms interact proportionally.
 */
function calculateRawScore(provider, weights) {
  // Normalize price term: (0.001 / basePrice) maps basePrice $0.001 -> 1.0, $0.005 -> 0.2
  const priceTerm = (0.001 / provider.basePrice) * 100;
  const priceScore = priceTerm * weights.price;

  // Normalize speed term: (1000 / avgLatencyMs) maps 120ms -> 8.33, 850ms -> 1.17
  const speedTerm = (1000 / provider.avgLatencyMs) * 10;
  const speedScore = speedTerm * weights.speed;

  // Reputation term: maps 0.80 -> 80
  const repTerm = provider.reputation * 100;
  const repScore = repTerm * weights.reputation;

  return priceScore + speedScore + repScore;
}

/**
 * Scores and ranks an array of alive providers.
 * Normalizes scores so the top provider scores in the 80-95 percentage range
 * and lower-ranked providers scale proportionally for clean UI presentation.
 * 
 * @param {Array} providers - List of alive provider objects
 * @param {string} mode - Optimization mode: "cheapest" | "fastest" | "balanced"
 * @returns {Array} List of provider objects with attached `score` property, sorted descending
 */
function scoreProviders(providers, mode) {
  const normalizedMode = (mode && WEIGHT_PROFILES[mode]) ? mode : "balanced";
  const weights = WEIGHT_PROFILES[normalizedMode];

  // Filter out any dead providers
  const aliveProviders = providers.filter(p => p.isAlive !== false);

  if (aliveProviders.length === 0) {
    return [];
  }

  // Calculate raw scores
  const scoredList = aliveProviders.map(provider => {
    const rawScore = calculateRawScore(provider, weights);
    return {
      provider,
      rawScore
    };
  });

  // Find maximum raw score among candidate providers
  const maxRawScore = Math.max(...scoredList.map(item => item.rawScore));

  // Target max score (94) to keep winning provider in 80-95 range
  const TARGET_TOP_SCORE = 94;

  const result = scoredList.map(item => {
    let finalScore = 0;
    if (maxRawScore > 0) {
      finalScore = Math.round((item.rawScore / maxRawScore) * TARGET_TOP_SCORE);
      // Floor at 15 and cap at 99 for realistic presentation
      finalScore = Math.max(15, Math.min(99, finalScore));
    }

    return {
      ...item.provider,
      score: finalScore
    };
  });

  // Sort descending by score
  result.sort((a, b) => b.score - a.score);

  return result;
}

module.exports = {
  WEIGHT_PROFILES,
  scoreProviders,
  calculateRawScore
};
