// Metric tooltips dictionary (EN). Shared across dashboards.
// Exposes window.METRIC_DESCRIPTIONS for reuse in templates.

(function(){
  const DESC = {
    // Usage
    'minutes': 'Total minutes played in the season',
    'minutes_90s': 'Number of 90-minute equivalents played',
    'games': 'Games played in the season',
    'starts': 'Games started in the season',

    // Attacking
    'goals': 'Goals scored in the season',
    'assists': 'Assists in the season',
    'expected_goals': 'Expected goals (xG)',
    'expected_assists': 'Expected assists (xA)',

    // Per 90
    'goals_per90': 'Goals per 90 minutes',
    'assists_per90': 'Assists per 90 minutes',
    'goals_assists_per90': 'Goals + Assists per 90 minutes',
    'expected_goals_per90': 'Expected goals per 90 minutes',
    'expected_assists_per90': 'Expected assists per 90 minutes',
    'expected_goals_assists_per90': 'Expected goals + assists per 90 minutes',

    // Progression
    'progressive_carries': 'Ball carries that move the ball significantly forward',
    'progressive_passes': 'Passes that move the ball significantly forward',
    'progressive_passes_received': 'Progressive passes received',

    // Passing
    'passes_completed': 'Completed passes',
    'passes': 'Passes attempted',
    'passes_pct': 'Completed passes percentage',
    'passes_completed_long': 'Long passes completed',
    'passes_long': 'Long passes attempted',
    'passes_pct_long': 'Long passes completion percentage',

    // Defending
    'tackles': 'Tackles made',
    'tackles_won': 'Tackles won',
    'interceptions': 'Interceptions',
    'blocks': 'Blocks',
    'blocked_shots': 'Shots blocked',
    'blocked_passes': 'Passes blocked',
    'clearances': 'Clearances',
    'challenge_tackles': 'Defensive challenges attempted',
    'challenges': 'Challenges attempted',
    'challenge_tackles_pct': 'Challenge success percentage',
    'challenges_lost': 'Challenges lost',
    'errors': 'Errors leading to shot/goal',
    'tackles_interceptions': 'Tackles + interceptions',

    // Goalkeeping
    'gk_goals_against': 'Goals conceded (GK)',
    'gk_pens_allowed': 'Penalty goals conceded (GK)',
    'gk_psxg': 'Post-shot expected goals faced (GK)',
    'gk_psnpxg_per_shot_on_target_against': 'Non-penalty xG per shot on target against (GK)',
    'gk_free_kick_goals_against': 'Free-kick goals conceded (GK)',
    'gk_corner_kick_goals_against': 'Corner-kick goals conceded (GK)',
    'gk_own_goals_against': 'Own goals conceded (GK)'
  };

  window.METRIC_DESCRIPTIONS = DESC;
})();


