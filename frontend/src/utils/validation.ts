/** Формат идентификатора эвиденции: TERYT_obręb.numer, напр. 141201_1.0001.6509 */
const PARCEL_ID_RE = /^\d{6}_\d\.\d{4}\.[\w/.-]+$/;

export const isParcelId = (s: string): boolean => PARCEL_ID_RE.test(s.trim());
