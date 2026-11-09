// Where in Pakistan someone works; the codes the API uses.
export const PROVINCES = ['ICT', 'PB', 'SD', 'KP', 'BA', 'AJK', 'GB'] as const;

// Nationalities offered on the employee form, most common in the region first; the names come
// from the browser in the screen's language.
export const NATIONALITIES = [
  'AE',
  'SA',
  'PK',
  'IN',
  'BD',
  'PH',
  'EG',
  'LK',
  'NP',
  'JO',
  'SY',
  'LB',
  'YE',
  'SD',
  'OM',
  'KW',
  'BH',
  'QA',
  'AF',
  'ID',
  'IR',
  'ET',
  'KE',
  'NG',
  'GB',
  'US',
] as const;

// The Gulf countries whose labour law builds up an end-of-service gratuity.
export const GRATUITY_COUNTRIES = ['AE', 'SA'];
