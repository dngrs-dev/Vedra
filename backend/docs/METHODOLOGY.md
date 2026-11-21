# Methodology

## Weather observations and model data

The weather series uses Open-Meteo ERA5-Seamless from 1 January 1991. The prototype caches complete
archive results by 0.1° cell and archive end date. It averages hourly soil moisture by local day
and converts daily daylight and sunshine seconds to hours. The recent gap in ERA5 publication uses
daily values from the forecast API. Recent soil moisture remains unavailable until the ERA5-Land
data arrive. All calculations cut off at the selected local analysis date.
[Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) and
[Forecast API](https://open-meteo.com/en/docs).

## Climatic water balance

The assessment compares the latest completed six-decade period with the crop and soil threshold
from the annex to [Dz.U. 2019 poz. 739](https://eli.gov.pl/api/acts/DU/2019/739/text.pdf). The drought
criterion is strictly below the threshold, as specified in article 3(2)(10) of the crop insurance act.
[Dz.U. 2019 poz. 477](https://eli.gov.pl/api/acts/DU/2019/477/text/I/D20190477.pdf).
The statutory `x` and `-` markers are reported separately. The history attributes each completed
period to its ending month and divides the number of drought periods by the number with a numeric
verdict. The data window ends on the selected analysis date.

The prototype subtracts monthly Doroszewski–Górski potential evapotranspiration from total
precipitation. It apportions monthly ETP by the calendar days covered by the period. When a period
ends mid-month, observed days up to the period end supply the temperature mean and daily sunshine
mean. The sunshine mean is multiplied by the full month's day count. The 15th represents mid-month
daylight. If that day falls after the cutoff or its daylight is missing, the calculation uses
astronomical daylight from the parcel latitude. A missing temperature or sunshine day leaves the
primary estimate unavailable. [IUNG, equations (1) and (2)](https://iung.pl/images/wyd/Susza%20rolnicza%20w%20Polsce.pdf)
and [FAO-56, chapter 3](https://www.fao.org/4/x0490e/x0490e07.htm).

The daily FAO-56 reference evapotranspiration supplies a parallel water balance. The prototype
flags a borderline result when the statutory threshold lies between the two balances, or when the
primary balance equals it. The spread describes sensitivity to the ETP method. Official SMSR
determinations use IUNG's own weather inputs and estimation methodology.
[IUNG SMSR](https://susza.iung.pulawy.pl/system/).

## Corroborating signals and causes

SPI-1 and SPI-3 use complete months. A separate gamma distribution is fitted for each calendar
month of the accumulation end within the 1991–2020 reference. Months with zero rainfall contribute
an empirical probability mass. A shorter available reference gives an indicative result with its
sample count. [McKee et al. (1993)](https://www.droughtmanagement.info/literature/AMS_Relationship_Drought_Frequency_Duration_Time_Scales_1993.pdf)
and [WMO-No. 1090](https://www.droughtmanagement.info/literature/WMO_standardized_precipitation_index_user_guide_en_2012.pdf).

Soil moisture uses the latest available ERA5-Land value at or before the selected date. It
compares each layer against the same calendar day in the previous ten years. The 20th percentile
from the European Climate Data Explorer soil drought product is used here as an indicative cutoff
for daily layer values. The report gives the observation date and sample counts.
[ECMWF European Climate Data Explorer](https://confluence.ecmwf.int/spaces/CKB/pages/453680707).

The satellite signal computes a parcel VCI from the median NDVI in the current window and the
minimum and maximum of the annual medians for comparable windows. Crop-sensitive dates use the
statutory KBW windows as a proxy, since sowing, emergence and harvest dates are usually unknown.
POLSA §6.3.4 describes phenological effects qualitatively. The numeric VCI interpretation uses
the NOAA STAR experimental cutoffs as indicative values for the prototype's parcel-scale index.
[FAO VCI definition](https://www.fao.org/giews/earthobservation/asis/index_2.jsp?lang=en),
[POLSA handbook](https://polsa.gov.pl/wp-content/themes/polsa/files/Podrecznik.pdf#page=293) and
[NOAA STAR VCI](https://www.star.nesdis.noaa.gov/smcd/emb/vci/VH/vh_browseByCountry_province.php).

Confidence uses two different forms of corroboration, modelled deep-layer soil moisture and
satellite vegetation. ERA5-Land and ERA5 share atmospheric forcing, so this is a qualitative
confidence level. SPI reuses the precipitation input and CDI combines several regional inputs.
Both appear as context. The model-derived runoff and land-cover findings describe possible local
contributors. The ranking places the strongest quantified weather departures first, followed by
soil, runoff, surroundings and crop demand. Historical NDVI comparisons use completed April–August
seasons, with sample counts for both sets of years.
[Copernicus EDO CDI](https://drought.emergency.copernicus.eu/data/factsheets/factsheet_combinedDroughtIndicator_v4.pdf).

## Dates outside the monitoring season

For dates outside 21 March through 30 September, the current KBW returns an off-season result.
Weather, soil moisture and EDO remain available as descriptive context, and recent satellite
observations are interpreted with crop dates in mind. History includes the completed windows
available before the analysis. The report omits current deficit causes and gives an off-season
explanation when irrigation is requested. [Statutory annex](https://eli.gov.pl/api/acts/DU/2019/739/text.pdf).
