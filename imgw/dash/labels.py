"""Polish labels ported from dane.meteomodel.pl (descriptions.js, utils-*.js,
monthly selector). Generated once from the site's JS; edit freely."""

MONTHLY_VARS = {'tm': 'Średnia temperatura',
 'tm2': 'Średnia temperatura (tx+tn)/2',
 'tx': 'Średnia temperatura maksymalna',
 'tn': 'Średnia temperatura minimalna',
 'txx': 'Najwyższa temperatura maksymalna',
 'tnn': 'Najniższa temperatura minimalna',
 'txn': 'Najniższa temperatura maksymalna',
 'tnx': 'Najwyższa temperatura minimalna',
 'tmx': 'Najwyższa temperatura średnia',
 'tmn': 'Najniższa temperatura średnia',
 'tgn': 'Temperatura minimalna przy gruncie',
 'prcp': 'Suma opadu',
 'prcpx': 'Najwyższa dobowa suma opadu',
 'mslp': 'Średnie ciśnienie (poziom morza)',
 'ppp': 'Średnie ciśnienie (poziom stacji)',
 'wind_speed': 'Średnia prędkość wiatru',
 'sunshine': 'Usłonecznienie',
 'rh': 'Średnia wilgotność',
 'vapp': 'Średnia prężność pary wodnej',
 'snow_depth': 'Suma dobowych wysokości pokrywy śnieżnej',
 'sndpx': 'Maksymalna wysokość pokrywy śnieżnej',
 'hdd': 'Heating degree days',
 'cdd': 'Cooling degree days',
 'gdd': 'Growing degree days',
 'hot': 'Liczba dni upalnych (percentyl)',
 'txgt35': 'Liczba dni z Tmax ≥ 35',
 'txgt30': 'Liczba dni z Tmax ≥ 30',
 'txgt25': 'Liczba dni z Tmax ≥ 25',
 'txgt20': 'Liczba dni z Tmax ≥ 20',
 'txgt15': 'Liczba dni z Tmax ≥ 15',
 'txgt10': 'Liczba dni z Tmax ≥ 10',
 'txlt10': 'Liczba dni z Tmax ≤ 10',
 'txlt0': 'Liczba dni z Tmax ≤ 0',
 'txltm10': 'Liczba dni z Tmax ≤ -10',
 'tngt10': 'Liczba dni z Tmin ≥ 10',
 'tngt15': 'Liczba dni z Tmin ≥ 15',
 'tngt20': 'Liczba dni z Tmin ≥ 20',
 'tnlt10': 'Liczba dni z Tmin ≤ 10',
 'tnlt0': 'Liczba dni z Tmin ≤ 0',
 'tnltm10': 'Liczba dni z Tmin ≤ -10',
 'tnltm20': 'Liczba dni z Tmin ≤ -20',
 'tnltm30': 'Liczba dni z Tmin ≤ -30',
 'sndpcnt': 'Liczba dni z pokrywą śnieżną'}

DAILY_VARS = {'tm': 'Średnia temperatura dobowa',
 'tx': 'Temperatura maksymalna',
 'tn': 'Temperatura minimalna',
 'tng': 'Temperatura minimalna przy gruncie',
 'rh': 'Wilgotność względna',
 'vapp': 'Prężność pary wodnej',
 'cloud_cover': 'Zachmurzenie [%]',
 'wind_speed': 'Średnia prędkość wiatru',
 'mslp': 'Ciśnienie na poziomie morza',
 'ppp': 'Ciśnienie na poziomie stacji',
 'prcp': 'Opad dobowy',
 'prcp_day': 'Opad dzień',
 'prcp_night': 'Opad noc',
 'snow_depth': 'Wysokość pokrywy śnieżnej [cm]',
 'snow_water': 'Równoważnik',
 'sunshine': 'Usłonecznienie',
 'ff10_time': 'Czas trwania wiatru ≥10 m/s',
 'ff15_time': 'Czas trwania wiatru ≥15 m/s',
 'ra_time': 'Czas trwania: Deszcz',
 'sn_time': 'Czas trwania: Śnieg',
 'rasn_time': 'Czas trwania: Deszcz+Śnieg',
 'fo_time': 'Czas trwania: Mgła',
 'dew_time': 'Czas trwania: Rosa',
 'frost_time': 'Czas trwania: Szron',
 'ts_time': 'Czas trwania: Burza'}

HOURLY_VARS = {'tm': 'Temperatura powietrza',
 'tx': 'Temperatura maksymalna',
 'tn': 'Temperatura minimalna',
 'tng': 'Temperatura minimalna przy gruncie',
 'rh': 'Wilgotność względna',
 'td': 'Temperatura punktu rosy',
 'wb': 'Temperatura termometru zwilżonego',
 'cloud_cover': 'Zachmurzenie [%]',
 'low_cloud_cover': 'Zachmurzenie przez chmury piętra niskiego [%]',
 'cl': 'Chmury piętra niskiego',
 'cm': 'Chmury piętra średniego',
 'ch': 'Chmury piętra wysokiego',
 'wind_speed': 'Prędkość wiatru',
 'wind_dir': 'Kierunek wiatru',
 'wind_gust': 'Prędkość wiatru w porywie',
 'mslp': 'Ciśnienie na poziomie morza',
 'ppp': 'Ciśnienie na poziomie stacji',
 'prcp': 'Suma opadu',
 'visib': 'Widzialność pozioma [km]',
 'visib_auto': 'Widzialność pozioma (automat) [km]',
 'sunshine': 'Usłonecznienie [h]',
 'ww': 'Pogoda bieżąca',
 'w1': 'Pogoda ubiegła'}

CLASS_NAMES = {1: 'ekstremalnie wysoka',
 2: 'anomalnie wysoka',
 3: 'bardzo wysoka',
 4: 'wysoka',
 5: 'dość (lekko) wysoka',
 6: 'normalna',
 7: 'dość (lekko) niska',
 8: 'niska',
 9: 'bardzo niska',
 10: 'anomalnie niska',
 11: 'ekstremalnie niska'}

WW_NAMES = {10: 'Zamglenie',
 11: 'Cienka warstwa mgły lub mgły lodowej, w płatach',
 12: 'Cienka warstwa mgły lub mgły lodowej, ciągła',
 13: 'Widoczna błyskawica, nie słychać grzmotu',
 14: 'Opad w polu widzenia nie sięgający gruntu',
 15: 'Opad w polu widzenia sięgający gruntu, ponad 5 km od stacji',
 16: 'Opad w polu widzenia sięgający gruntu, w pobliżu stacji lecz nie na stacji',
 17: 'Burza bez opadu w czasie obserwacji',
 18: 'Nawałnica na stacji lub w polu widzenia w czasie obserwacji lub w ciągu ostatniej godziny',
 19: 'Trąba lądowa lub wodna na stacji lub w polu widzenia w czasie obserwacji lub w ciągu '
     'ostatniej godziny',
 20: 'Mżawka (nie marznąca) lub śnieg ziarnisty',
 21: 'Deszcz (nie marznący)',
 22: 'Śnieg',
 23: 'Deszcz ze śniegiem lub ziarna lodowe',
 24: 'Mżawka marznąca lub deszcz marznący',
 25: 'Przelotny deszcz',
 26: 'Przelotny śnieg lub przelotny deszcz ze śniegiem',
 27: 'Pprzelotny grad lub deszcz z gradem lub krupy śnieżne lub krupy lodowe',
 28: 'Mgła lub mgła lodowa',
 29: 'Burza bez opadu lub z opadem',
 30: 'Słaba lub umiarkowana wichura pyłowa lub piaskowa, słabnąca w ciągu ostatniej godziny',
 31: 'Słaba lub umiarkowana wichura pyłowa lub piaskowa, bez zmian w ciągu ostatniej godziny',
 32: 'Słaba lub umiarkowana wichura pyłowa lub piaskowa, zaczynająca się lub wzmagająca w ciągu '
     'ostatniej godziny',
 33: 'Silna wichura pyłowa lub piaskowa, słabnąca w ciągu ostatniej godziny',
 34: 'Silna wichura pyłowa lub piaskowa, bez zmian w ciągu ostatniej godziny',
 35: 'Silna wichura pyłowa lub piaskowa, zaczynająca się lub wzmagająca w ciągu ostatniej godziny',
 36: 'Słaba lub umiarkowana zamieć śnieżna niska',
 37: 'Silna zamieć śnieżna niska',
 38: 'Słaba lub umiarkowana zamieć śnieżna wysoka',
 39: 'Silna zamieć śnieżna wysoka',
 40: 'Mgła (mgła lodowa) w pewnej odległości od stacji w czasie obserwacji, sięgająca powyżej '
     'poziomu oczu, w ciągu ostatniej godziny mgły na stacji nie było',
 41: 'Mgła (mgła lodowa) w płatach',
 42: 'Mgła (mgła lodowa), niebo widoczne, staje się rzadsza',
 43: 'Mgła (mgła lodowa), niebo niewidoczne, staje się rzadsza',
 44: 'Mgła (mgła lodowa), niebo widoczne, bez zmian w ciągu ostatniej godziny',
 45: 'Mgła (mgła lodowa), niebo niewidoczne, bez zmian w ciągu ostatniej godziny',
 46: 'Mgła (mgła lodowa), niebo widoczne, gęstnieje',
 47: 'Mgła (mgła lodowa), niebo niewidoczne, gęstnieje',
 48: 'Mgła osadzająca szadź, niebo widoczne',
 49: 'Mgła osadzająca szadź, niebo niewidoczne',
 50: 'Słaba, niemarznąca mżawka z przerwami',
 51: 'Słaba, niemarznąca, ciągła mżawka',
 52: 'Umiarkowana, niemarznąca mżawka z przerwami',
 53: 'Umiarkowana, niemarznąca, ciągła mżawka',
 54: 'Intensywna, niemarznąca mżawka z przerwami',
 55: 'Intensywna, niemarznąca, ciągła mżawka',
 56: 'Słaba marznąca mżawka',
 57: 'Umiarkowana lub silna marznąca mżawka',
 58: 'Słaba mżawka z deszczem',
 59: 'Umiarkowana lub silna mżawka z deszczem',
 60: 'Niemarznący, słaby deszcz z przerwami',
 61: 'Niemarznący, słaby, ciągły',
 62: 'Niemarznący, umiarkowany deszcz z przerwami',
 63: 'Niemarznący, umiarkowany, ciągły deszcz',
 64: 'Niemarznący, silny deszcz z przerwami',
 65: 'Niemarznący, silny, ciągły deszcz',
 66: 'Słaby marznący deszcz',
 67: 'Umiarkowany lub silny marznący deszcz',
 68: 'Słaby deszcz ze śniegiem',
 69: 'Umiarkowany lub silny deszcz ze śniegiem',
 70: 'Słaby śnieg z przerwami',
 71: 'Słaby, ciągły śnieg',
 72: 'Umiarkowany śnieg z przerwami',
 73: 'Umiarkowany, ciągły śnieg',
 74: 'Silny śnieg z przerwami',
 75: 'Silny, ciągły śnieg',
 76: 'Pył diamentowy',
 77: 'Śnieg ziarnisty',
 78: 'Oddzielne gwiazdki śniegu',
 79: 'Ziarna lodowe',
 80: 'Słaby przelotny deszcz',
 81: 'Umiarkowany lub silny przelotny deszcz',
 82: 'Gwałtowny przelotny deszcz',
 83: 'Słaby przelotny deszcz ze śniegiem',
 84: 'Umiarkowany lub silny przelotny deszcz ze śniegiem',
 85: 'Słaby przelotny śnieg',
 86: 'Umiarkowany lub silny przelotny śnieg',
 87: 'Słabe przelotne krupy lodowe lub śnieżne',
 88: 'Umiarkowane lub silne, przelotne krupy lodowe lub śnieżne',
 89: 'Słaby przelotny grad',
 90: 'Umiarkowany lub silny przelotny grad',
 91: 'Burza w ciągu ostatniej godziny, w czasie obserwacji lekki deszcz',
 92: 'Burza w ciągu ostatniej godziny, w czasie obserwacji umiarkowany lub silny deszcz',
 93: 'Burza w ciągu ostatniej godziny, w czasie obserwacji lekki śnieg lub deszcz ze śniegiem',
 94: 'Burza w ciągu ostatniej godziny, w czasie obserwacji umiarkowany lub silny śnieg lub deszcz '
     'ze śniegiem',
 95: 'Słaba lub umiarkowana burza w czasie obserwacji',
 96: 'Słaba lub umiarkowana burza z gradem w czasie obserwacji',
 97: 'Silna burza',
 98: 'Silna burza z wichurą pyłową lub piaskową',
 99: 'Silna burza z gradem',
 0: 'Rozwój chmur nieznany',
 1: 'Chmury zanikają lub stają się cieńsze',
 2: 'Stan nieba nie zmienia się',
 3: 'Chmury w stadium tworzenia się lub rozwoju',
 4: 'Widzialność zmniejszona przez dym (z pożarów lasów, stepów, dymy pochodzenia fabrycznego lub '
    'pyły wulkaniczne)',
 5: 'Zmętnienie (zmniejszenie widzialności spowodowane głównie przez litometeory)',
 6: 'Pył w powietrzu (nie wzniesiony przez wiatr w czasie obserwacji)',
 7: 'Pył lub piasek w powietrzu wznoszony przez wiatr',
 8: 'Silnie rozwinięte wiry pyłowe lub piaskowe na stacji lub w pobliżu, w czasie obserwacji lub w '
    'ciągu ostatniej godziny, nie wichura pyłowa lub piaskowa',
 9: 'Wichura pyłowa lub piaskowa w zasięgu widzenia w czasie obserwacji lub na stacji w ciągu '
    'ostatniej godziny'}

CLOUD_NAMES = {'cl': {'0': 'Brak',
        '1': 'Cumulus humilis lub Cumulus fractus (ale nie złej pogody) lub obie chmury razem',
        '2': 'Cumulus mediocris lub congestus występujący sam lub z Cu hum lub Cu fra bądź też ze '
             'Stratocumulus; wszystkie chmury na tym samym poziomie',
        '3': 'Cumulonimbus calvus (sam lub z Cu, Sc lub St)',
        '4': 'Stratocumulus cumulogenitus',
        '5': 'Stratocumulus (lecz nie cumulogenitus)',
        '6': 'Stratus nebulosus lub Stratus fractus (lecz nie złej pogody) lub obie chmury razem',
        '7': 'Stratus fractus lub Cumulus fractus (złej pogody) lub obie chmury razem (pannus), '
             'zwykle pod Altostratus lub Nimbostratus',
        '8': 'Cumulus i Stratocumulus (lecz nie Stratocumulus cumulogenitus) o podstawach na '
             'różnych poziomach',
        '9': 'Cumulonimbus capillatus (często z kowadłem) występujący sam lub z Cumulonimbus '
             'calvus, Cumulus, Stratocumulus, Stratus lub pannus',
        '/': 'chmury nie były widoczne (ciemność, mgła)'},
 'cm': {'0': 'Brak',
        '1': 'Altostratus translucidus',
        '2': 'Altostratus opacus lub Nimbostratus',
        '3': 'Altocumulus translucidus na jednym poziomie',
        '4': 'ławice Altocumulus translucidus, często soczewkowate, ciągle zmieniające się i '
             'występujące na jednym lub kilku poziomach',
        '5': 'Altocumulus translucidus w pasmach, albo jedna lub więcej warstw Altocumulus '
             'translucidus lub opacus, stopniowo zaciągająca niebo; te chmury Ac na ogół w całości '
             'grubieją',
        '6': 'Altocumulus cumulogenitus (lub cumulonimbogenitus)',
        '7': 'Altocumulus translucidus lub opacus w dwóch lub więcej warstwach, lub Altocumulus '
             'opacus w pojedynczej warstwie, nie zaciągający nieba lub Altocumulus z Altostratus '
             'lub Nimbostratus',
        '8': 'Altocumulus castellanus lub floccus',
        '9': 'Altocumulus na niebie o wyglądzie chaotycznym, na ogół na kilku poziomach',
        '/': 'chmury nie były widoczne (ciemność, mgła, ciągła warstwa chmur niskich)'},
 'ch': {'0': 'Brak',
        '1': 'Cirrus fibratus lub Cirrus uncinus (nie zaciągający nieba)',
        '2': 'Cirrus spissatus w ławicach lub w postaci poplątanych wiązek, albo Cirrus '
             'castellanus lub floccus',
        '3': 'Cirrus spissatus cumulonimbogenitus',
        '4': 'Cirrus uncinus lub Cirrus fibratus lub obie te chmury razem (stopniowo zaciągający '
             'niebo)',
        '5': 'Cirrus (w pasmach) i Cirrostratus lub sam Cirrostratus stopniowo zaciągający niebo, '
             'ale nie wyżej niż 45° nad horyzontem',
        '6': 'Cirrus (w pasmach) i Cirrostratus lub sam Cirrostratus stopniowo zaciągający niebo, '
             'powyżej niż 45° nad horyzontem, lecz nie pokrywa całkowicie nieba',
        '7': 'Cirrostratus pokrywający całkowicie niebo',
        '8': 'Cirrostratus nie zaciągający i nie pokrywający nieba',
        '9': 'Cirrocumulus sam lub przeważający wśród chmur wysokich',
        '/': 'Chmury nie były widoczne (ciemność, mgła, ciągła warstwa chmur niższych)'}}

DESCRIPTIONS = {'tm': 'Średnia temperatura dobowa. Od 1966 r. na stacjach synoptycznych (id = 3xxxxxxxx) '
       'wyliczana z 8 terminów na dobę w czasie UTC (wcześniej wg wzoru [T06 + T12 + 2*T20]/4 w '
       'czasie GMT). Na stacjach klimatologicznych (id = 2xxxxxxxx) do 1971 roku wyliczana wg '
       'wzoru [T06 + T12 + 2*T20]/4 w czasie GMT, od 1971 do 1996 wg wzoru [T00 + T06 + T12 + '
       'T18]/4, od 1996 wg [T06 + T18 + Tmax + Tmin]/4',
 'tx': 'Średnia miesięczna temperatura maksymalna (średnia z Tmax dobowych). Od 1966 r. Tmax '
       'dobowa mierzona między 18UTC dnia poprzedniego a 18UTC dnia bieżącego. Wcześniej progiem '
       'była godzina 20UTC (na stacjach klimatologicznych do 1971).',
 'txx': 'Najwyższa miesięczna temperatura maksymalna (maksimum z Tmax dobowych). Od 1966 r. Tmax '
        'dobowa mierzona między 18UTC dnia poprzedniego a 18UTC dnia bieżącego. Wcześniej progiem '
        'była godzina 20UTC (na stacjach klimatologicznych do 1971).',
 'txn': 'Najniższa miesięczna temperatura maksymalna (minimum z Tmax dobowych). Od 1966 r. Tmax '
        'dobowa mierzona między 18UTC dnia poprzedniego a 18UTC dnia bieżącego. Wcześniej progiem '
        'była godzina 20UTC (na stacjach klimatologicznych do 1971).',
 'tn': 'Średnia miesięczna temperatura minimalna (średnia z Tmax dobowych). Od 1966 r. Tmin dobowa '
       'mierzona między 18UTC dnia poprzedniego a 18UTC dnia bieżącego. Wcześniej progiem była '
       'godzina 20UTC (na stacjach klimatologicznych do 1971).',
 'tnn': 'Najniższa miesięczna temperatura minimalna (minimum z Tmin dobowych). Od 1966 r. Tmin '
        'dobowa mierzona między 18UTC dnia poprzedniego a 18UTC dnia bieżącego. Wcześniej progiem '
        'była godzina 20UTC (na stacjach klimatologicznych do 1971).',
 'tnx': 'Najwyższa miesięczna temperatura minimalna (maksimum z Tmin dobowych). Od 1966 r. Tmin '
        'dobowa mierzona między 18UTC dnia poprzedniego a 18UTC dnia bieżącego. Wcześniej progiem '
        'była godzina 20UTC (na stacjach klimatologicznych do 1971).',
 'hdd': 'Liczba stopniodni grzewczych wyliczona jako suma różnicy miedzy średnią temperaturą '
        'dobową (Tm) a wartością 18.0 dla Tm <= 15.0°C.',
 'cdd': 'Liczba stopniodni chłodzenia wyliczona jako suma różnicy miedzy średnią temperaturą '
        'dobową (Tm) a wartością 18.0 dla Tm > 18.0°C.',
 'gdd': 'Suma temperatur efektywnych wyliczona jako suma różnicy miedzy średnią temperaturą dobową '
        '(Tm) a wartością 10.0 dla Tm > 10.0°C.',
 'prcp': 'Miesięczna suma opadu (suma z dobowych sum opadu). Dobowa suma opadu mierzona jest o '
         '06UTC, przy czym opad przypisywany jest do doby poprzedniej.',
 'sunshine': 'Miesięczna suma usłonecznienia. Do 2011-2013 roku na większości stacji '
             'usłonecznienie mierzono heliografem Campbella-Stokesa, po tym czasie został on '
             'zastąpiony przez czujniki elektroniczne.',
 'hot': 'Liczba dni upalnych wyliczona jako liczba dni z temperaturą wyższą lub równą 95 '
        'percentylowi Tmax z miesięcy czerwiec-sierpień 1981-2020. Wartość percentyla będzie różna '
        'dla róznych stacji. Np. dla Wrocławia wynosi ona 31.6°C, dla Helu 27.1°C, dla Śnieżki '
        '19.7°C. Na podstawie: Ustrnul Z., Czekierda D., Wypych A. Extreme values of air '
        'temperature in Poland according to different atmospheric circulation classifications. ", '
        'Physics and Chemistry of the Earth, Parts A/B/C, Volume 35, Issues 9–12 2010, p 429-436.'}
