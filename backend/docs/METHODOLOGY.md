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
