# Frontier tool-call transcripts

Model `Qwen/Qwen2.5-72B-Instruct`, 4-bit. Sample size 8. k=10.
Ground truth is the tool the model called on the full menu.
Keyword search, original Open-Jev-2B, and tuned 2B each keep 10 tools, and the same model calls one tool from that menu.
Hosted Jev is the TypeSafe API (`jev-latest`), not the local Open-Jev-2B checkpoint.
It chooses one tool from the same 50-tool menu. Accuracy is whether that choice matches the full-menu call.
The hosted arm did not start another GPU. Its API cost is separate from the Modal bill.

## train_59141

I'm planning a trip to New York City and I would like to know the current location of the International Space Station. Additionally, please provide me with the supported regions for phone formatting in the United States.

| Arm | Tools shown | Called | Matched full menu | Seconds |
| --- | ---: | --- | --- | ---: |
| full menu | 50 | Get_ISS_Location, simpleRegions | yes | 4.80 |
| keyword search | 10 | Get_ISS_Location, simpleRegions | yes | 4.32 |
| original Open-Jev-2B top 10 | 10 | Get_ISS_Location, Phone_Formatter_regions | yes | 2.80 |
| tuned 2B top 10 | 10 | Get_ISS_Location, Phone_Formatter_regions | yes | 2.74 |
| hosted Jev top 10 | 10 | Get_ISS_Location | yes | 0.18 |

### full menu

Menu: Get_ISS_Location, Domain_WHOIS_Lookup_API_domain_name, simpleRegions, Free_Phone_Carrier_Lookup_Carrier_Endpoint, United_States_COVID-19_New_Case_Count_API, United_States_COVID-19_New_Death_Count_API, United_States_COVID-19_New_Test_Count_API, Broadway, COVID_19_Economic_Impact_United_States_COVID_19_, COVID_19_Economic_Impact_United_States_COVID_19__2, Phone_Number_Validation_and_Formatting, checkthatphone, CheckThatPhone_checkthatphone, Search_States_by_Capital, Trip_s_Current_Status, TripPlan, EzcqyoXYRX, optionD_data, options_data, optBionus_datTa, getInteractiveVisualizations, options_data_2, Get_New_York_Lottery_Draw_Results, Get_Supported_Regions, Today_s_International_Current_Affairs, United_States_Scheduled_Flights_Growth_API, United_States_COVID-19_Case_Count, Supported_Languages_and_Regions, RapidWeather_By_city_name, HM_Hennes_Mauritz_regions_list, regions_list, international_meeting_planner, find_closest_gas_station, Webull_regions_list, Canadian_Gas_Prices_City, United_States_COVID-19_Death_Count_API, United_States_Job_Postings_API, Get_United_States_Continued_Claims_Count, regions, United_States_Residential_Mobility_API, Gas_Price_stateUsaPrice, update_location, Google_Trends_regions, United_States_Card_Spending, regions_2, location_Loc, Global_Flight_Data_United_States_Scheduled_Fligh, Global_Flight_Data_United_States_Scheduled_Fligh_2, ISS_Location_get, Phone_Formatter_regions

```
<tool_call>
{"name": "Get_ISS_Location", "arguments": {}}
</tool_call>
<tool_call>
{"name": "simpleRegions", "arguments": {"type": "Accept-Language", "properties": "en-US", "required": "Accept-Language"}}
</tool_call>
```

### keyword search

Menu: Get_ISS_Location, Domain_WHOIS_Lookup_API_domain_name, simpleRegions, Free_Phone_Carrier_Lookup_Carrier_Endpoint, United_States_COVID-19_New_Case_Count_API, United_States_COVID-19_New_Death_Count_API, United_States_COVID-19_New_Test_Count_API, Broadway, COVID_19_Economic_Impact_United_States_COVID_19_, COVID_19_Economic_Impact_United_States_COVID_19__2

```
<tool_call>
{"name": "Get_ISS_Location", "arguments": {"type": "object", "properties": "", "required": ""}}
</tool_call>
<tool_call>
{"name": "simpleRegions", "arguments": {"type": "object", "properties": "Accept-Language: en-US", "required": "Accept-Language"}}
</tool_call>
```

### original Open-Jev-2B top 10

Menu: Get_ISS_Location, ISS_Location_get, simpleRegions, Phone_Number_Validation_and_Formatting, Supported_Languages_and_Regions, Webull_regions_list, CheckThatPhone_checkthatphone, RapidWeather_By_city_name, update_location, Phone_Formatter_regions

```
<tool_call>
{"name": "Get_ISS_Location", "arguments": {}}
</tool_call>
<tool_call>
{"name": "Phone_Formatter_regions", "arguments": {"type": "en-US"}}
</tool_call>
```

### tuned 2B top 10

Menu: Get_ISS_Location, simpleRegions, Phone_Formatter_regions, Get_Supported_Regions, location_Loc, ISS_Location_get, Webull_regions_list, regions, regions_2, regions_list

```
<tool_call>
{"name": "Get_ISS_Location", "arguments": {}}
</tool_call>
<tool_call>
{"name": "Phone_Formatter_regions", "arguments": {"language": "en-US"}}
</tool_call>
```

### hosted Jev top 10

Top 10: Get_ISS_Location, simpleRegions, Phone_Number_Validation_and_Formatting, ISS_Location_get, Phone_Formatter_regions, Domain_WHOIS_Lookup_API_domain_name, Free_Phone_Carrier_Lookup_Carrier_Endpoint, United_States_COVID-19_New_Case_Count_API, United_States_COVID-19_New_Death_Count_API, United_States_COVID-19_New_Test_Count_API

## train_31862

Retrieve geolocation data for IP addresses 8.8.8.8 and 2404:6800:4009:805::200e.

| Arm | Tools shown | Called | Matched full menu | Seconds |
| --- | ---: | --- | --- | ---: |
| full menu | 50 | getGeolocationDetailsList | yes | 4.88 |
| keyword search | 10 | getGeolocationDetailsList | yes | 3.57 |
| original Open-Jev-2B top 10 | 10 | bulkGeolocationLookup | no | 3.47 |
| tuned 2B top 10 | 10 | bulkGeolocationLookup | no | 3.47 |
| hosted Jev top 10 | 10 | bulkGeolocationLookup | no | 0.21 |

### full menu

Menu: bulkGeolocationLookup, batchLookup, getGeolocation, getGeolocationDetailsList, getGeoIP, get_geolocation_data, Get_IP_Geolocation, geolocationLookup, ip_geolocation_lookup, IP_Geolocation_Find_IP_Location_and_IP_Info_Get_, IP_Geolocation_v3_Get_IP_Geolocation, getMyIP, IP_Geolocation, Greip_IPLookup, ip_address_lookup, IP_Geolocation_API_IP_Geolocation, IP_Geolocator_IP_lookup, ip_lookup, IP_Geolocation_and_Reputation_API, get_ip_geolocation, IP2Currency_IP2Currency_API, Get_IP_Addresses, IP_Geolocation_API, Location_Get_the_addresses_by_IP, IP_Address_Geolocation_IP_Geolocation, Abstract_IP_geolocation_Geolocation_from_an_IP_A, getGeoLocation, IP_Lookup, getMailServers, getNameServers, getGeolocationDetails, Multiple_IP_Detection_V2, Get_Geolocation_by_IP, searchIP, IP_Geolocation_Lookup, shw_geolocation_api_get_geolocation_data, ip_locator, getGeolocationPosition, ip_geolocation, ip, format, IP_Address_Geolocation_API, Spott_Get_place_by_IP, searchIpAddress, Get_Place_by_IP, Read_Usage_Per_IP, IP2Proxy_API, Bulk_WHOIS, GeoLocation2TimeZone, IP_Geolocation_Lookup_2

```
<tool_call>
{"name": "getGeolocationDetailsList", "arguments": {"ip_addresses": "8.8.8.8,2404:6800:4009:805::200e"}}
</tool_call>
```

### keyword search

Menu: bulkGeolocationLookup, batchLookup, getGeolocation, getGeolocationDetailsList, getGeoIP, get_geolocation_data, Get_IP_Geolocation, geolocationLookup, ip_geolocation_lookup, IP_Geolocation_Find_IP_Location_and_IP_Info_Get_

```
<tool_call>
{"name": "getGeolocationDetailsList", "arguments": {"ip_addresses": "8.8.8.8,2404:6800:4009:805::200e"}}
</tool_call>
```

### original Open-Jev-2B top 10

Menu: IP_Geolocation_v3_Get_IP_Geolocation, IP_Geolocation_Find_IP_Location_and_IP_Info_Get_, IP_Geolocator_IP_lookup, IP_Lookup, Abstract_IP_geolocation_Geolocation_from_an_IP_A, IP_Geolocation_Lookup, Get_Geolocation_by_IP, Get_IP_Geolocation, bulkGeolocationLookup, ip_lookup

```
<tool_call>
{"name": "bulkGeolocationLookup", "arguments": {"ip_addresses": "8.8.8.8,2404:6800:4009:805::200e"}}
</tool_call>
```

### tuned 2B top 10

Menu: get_ip_geolocation, getGeolocation, geolocationLookup, get_geolocation_data, getGeoLocation, ip_locator, ip_geolocation, Get_IP_Geolocation, shw_geolocation_api_get_geolocation_data, bulkGeolocationLookup

```
<tool_call>
{"name": "bulkGeolocationLookup", "arguments": {"ip_addresses": "8.8.8.8,2404:6800:4009:805::200e"}}
</tool_call>
```

### hosted Jev top 10

Top 10: bulkGeolocationLookup, getGeolocationDetailsList, batchLookup, getGeolocation, getGeoIP, get_geolocation_data, Get_IP_Geolocation, geolocationLookup, ip_geolocation_lookup, IP_Geolocation_Find_IP_Location_and_IP_Info_Get_

## train_102966

Please provide the top 2 news from CoinDesk and the average peer metrics for Microsoft's stock symbol.

| Arm | Tools shown | Called | Matched full menu | Seconds |
| --- | ---: | --- | --- | ---: |
| full menu | 50 | crypto_news_v2_Top_News, peer_metrics_average | yes | 4.57 |
| keyword search | 10 | crypto_news_v2_Top_News, peer_metrics_average | yes | 3.14 |
| original Open-Jev-2B top 10 | 10 | crypto_news_v2_Top_News, peer_metrics_average | yes | 3.77 |
| tuned 2B top 10 | 10 | crypto_news_v2_Top_News, peer_metrics_average | yes | 4.29 |
| hosted Jev top 10 | 10 | crypto_news_v2_Top_News | yes | 0.13 |

### full menu

Menu: MarketCI_Analytics_Peer_Metrics_Average, Cryptocurrency_News_CoinDesk, peer_metrics_average, Peer_Ratio_Averages, CoinDesk_News_API, crypto_news_v2_Top_News, symbols_get_peers, List_Top_News, crypto_news_v2_CoinDesk, Top_News_API, peer_ratio_averages, MarketCI_Analytics_Peer_Ratio_Averages, news_list_top, Get_Yahoo_Finance_Stock_News, Symbols_Metrics, stock_get_annual_avg_div_yield, stock_get_annual_avg_div_rate, Get_News_by_Symbol, News_Feed_for_Symbol, Get_Latest_News_by_Symbol, symbols_get-sector-metrics, stock_get_five_yr_avg_div_yield, stock_get_50day_moving_avg, stock_news, Symbols_Sector_Metrics, stock_get_five_yr_avg_div_yield_2, Symbols_Financials_metrics, news_v2_list_by_symbol, key_metrics, Get_Annual_Average_Dividend_Rate, Cryptocurrency_News_BSC_News, Get_Top_Holdings, symbol, Get_Ten_Day_Average_Daily_Volume, Yahoo_Finance_News, Top_News_Fetcher, Get_Top_News, stock_time_series, Top_Match_Metrics, Crypto_News_v2_Get_Individual_News_Source, PolygonFinance_get_ticker_news, Stock_Time_Series_API, Microsoft_Translator, market_data, quote_get_margin_requirements, getStockQuotes, Cryptocurrency_News_Bitcoinist, Cryptocurrency_News_Decrypt, Cryptocurrency_News_The_Guardian, top_news

```
<tool_call>
{"name": "crypto_news_v2_Top_News", "arguments": {"number_of_articles": "2"}}
</tool_call>
<tool_call>
{"name": "peer_metrics_average", "arguments": {"symbol": "MSFT"}}
</tool_call>
```

### keyword search

Menu: MarketCI_Analytics_Peer_Metrics_Average, Cryptocurrency_News_CoinDesk, peer_metrics_average, Peer_Ratio_Averages, CoinDesk_News_API, crypto_news_v2_Top_News, symbols_get_peers, List_Top_News, crypto_news_v2_CoinDesk, Top_News_API

```
<tool_call>
{"name": "crypto_news_v2_Top_News", "arguments": {"count": 2}}
</tool_call>
<tool_call>
{"name": "peer_metrics_average", "arguments": {"symbol": "MSFT"}}
</tool_call>
```

### original Open-Jev-2B top 10

Menu: Top_News_API, crypto_news_v2_CoinDesk, Cryptocurrency_News_CoinDesk, CoinDesk_News_API, Symbols_Metrics, Peer_Ratio_Averages, symbols_get-sector-metrics, peer_metrics_average, crypto_news_v2_Top_News, Symbols_Sector_Metrics

```
<tool_call>
{"name": "crypto_news_v2_Top_News", "arguments": {"type": "object", "properties": {"limit": "2"}}}
</tool_call>
<tool_call>
{"name": "peer_metrics_average", "arguments": {"symbol": "MSFT"}}
</tool_call>
```

### tuned 2B top 10

Menu: peer_metrics_average, MarketCI_Analytics_Peer_Metrics_Average, crypto_news_v2_Top_News, Top_News_API, Get_Top_News, Top_News_Fetcher, Cryptocurrency_News_CoinDesk, CoinDesk_News_API, Peer_Ratio_Averages, List_Top_News

```
<tool_call>
{"name": "crypto_news_v2_Top_News", "arguments": {"type": "object", "properties": {"limit": 2}}}
</tool_call>
<tool_call>
{"name": "peer_metrics_average", "arguments": {"type": "object", "properties": {"symbol": "MSFT"}}}
</tool_call>
```

### hosted Jev top 10

Top 10: crypto_news_v2_Top_News, Top_News_API, Cryptocurrency_News_CoinDesk, peer_metrics_average, CoinDesk_News_API, peer_ratio_averages, MarketCI_Analytics_Peer_Metrics_Average, Peer_Ratio_Averages, Crypto_News_v2_Get_Individual_News_Source, symbols_get_peers

## train_32840

How much will my investment of $1000 grow to after 5 years at an interest rate of 3%?

| Arm | Tools shown | Called | Matched full menu | Seconds |
| --- | ---: | --- | --- | ---: |
| full menu | 50 | calculate_future_value | yes | 4.62 |
| keyword search | 10 | calculate_future_value | yes | 2.88 |
| original Open-Jev-2B top 10 | 10 | future_investment_value | no | 2.82 |
| tuned 2B top 10 | 10 | calculate_future_value | yes | 2.98 |
| hosted Jev top 10 | 10 | future_investment_value | no | 0.12 |

### full menu

Menu: calculate_ci, calculate_future_value, future_investment_value, calculate_annual_interest_rate_initial_investmen, calculate_compound_interest_principal_rate_time, compound_interest, calculate_annual_rate_of_interest, calculate_half_yearly_interest, find_investment_amount_option1_total_investment_, Car_Utils_Estimate_Ownership_Cost, calculate_total_interest_principal_rate_time, calculate_principal_amount, calculate_investment_return, cagr, investment_profit, CalcX_Investment_API_GET_Calculate_Investment, Calculate_Investment, calculate_years, calculate_simple_interest_per_year, calculateFutureValue, compound_interest_difference_principal_rate_time, calculate_final_balance, find_rate_percent, calculate_compound_interest_general_principal_ra, project_investment_growth, calculate_total_with_interest_original_amount_in, calculate_depreciation, find_younger_member_age, calculateInterest, calculate_total_amount, calculate_interest_rate, Interest_Rate_by_API_Ninjas_v1_interestrate, get_loan_interest_rate, fetch_deposit_rates, unemployment_rate_compare, calculate_monthly_payment, calculate_interest_amount, simple_interest, GetLoanInterestRate, project_population, finance_evaluateInvestmentReturn, calculate_final_value, calculate_initial_amount, calculate_cagr, calculate_compounding_factor, calculate_interest, predict_evolution_rate, calculate_time_to_double, calculate_simple_interest, calculate_compound_interest

```
<tool_call>
{"name": "calculate_future_value", "arguments": {"initial_amount": "1000", "interest_rate": "0.03", "num_years": "5"}}
</tool_call>
```

### keyword search

Menu: calculate_ci, calculate_future_value, future_investment_value, calculate_annual_interest_rate_initial_investmen, calculate_compound_interest_principal_rate_time, compound_interest, calculate_annual_rate_of_interest, calculate_half_yearly_interest, find_investment_amount_option1_total_investment_, Car_Utils_Estimate_Ownership_Cost

```
<tool_call>
{"name": "calculate_future_value", "arguments": {"initial_amount": "1000", "interest_rate": "0.03", "years": "5"}}
</tool_call>
```

### original Open-Jev-2B top 10

Menu: calculate_future_value, future_investment_value, calculate_investment_return, calculate_ci, calculate_compound_interest_principal_rate_time, calculate_compound_interest_general_principal_ra, calculate_final_balance, calculate_total_with_interest_original_amount_in, calculate_final_value, CalcX_Investment_API_GET_Calculate_Investment

```
<tool_call>
{"name": "future_investment_value", "arguments": {"present_value": "1000", "annual_interest_rate": "3", "years": "5"}}
</tool_call>
```

### tuned 2B top 10

Menu: calculate_investment_return, calculate_total_with_interest_original_amount_in, calculate_compound_interest_principal_rate_time, calculate_future_value, calculate_compound_interest_general_principal_ra, find_investment_amount_option1_total_investment_, Calculate_Investment, calculate_final_balance, CalcX_Investment_API_GET_Calculate_Investment, calculate_total_interest_principal_rate_time

```
<tool_call>
{"name": "calculate_future_value", "arguments": {"initial_amount": "1000", "interest_rate": "3", "num_years": "5"}}
</tool_call>
```

### hosted Jev top 10

Top 10: future_investment_value, calculate_future_value, calculate_ci, calculate_compound_interest_principal_rate_time, calculate_final_balance, calculate_final_value, calculate_annual_interest_rate_initial_investmen, compound_interest, calculate_annual_rate_of_interest, calculate_half_yearly_interest

## train_46254

I need a detailed cake recipe for 'cake789' and a side dish recipe with 'onions'.

| Arm | Tools shown | Called | Matched full menu | Seconds |
| --- | ---: | --- | --- | ---: |
| full menu | 50 | Get_Detailed_Cake_Recipe_by_ID, side_dish_ingredient | yes | 5.41 |
| keyword search | 10 | Get_Detailed_Cake_Recipe_by_ID, side_dish_ingredient | yes | 4.22 |
| original Open-Jev-2B top 10 | 10 | The_Birthday_Cake_DB_Detailed_Cake_Recipe_by_ID, Recipe_Finder_side_dish_ingredient | no | 4.07 |
| tuned 2B top 10 | 10 | detailed_cake_recipe_by_id, side_dish_ingredient | no | 3.45 |
| hosted Jev top 10 | 10 | Get_Detailed_Cake_Recipe_by_ID | yes | 0.16 |

### full menu

Menu: Get_Side_Dish_Recipe, Get_Detailed_Cake_Recipe_by_ID, detailed_cake_recipe_by_id, FindRecipe, The_Birthday_Cake_DB_Detailed_Cake_Recipe_by_ID, side_dish_ingredient, cake_ingredient, The_Birthday_Cake_DB_List_of_Cakes, Recipe_Detail, Get_Cake_Recipe_by_Ingredient, Get_Detailed_Cocktail_Recipe_by_ID, Get_Recipe_Details, Recipe_Finder_side_dish_ingredient, Get_Detailed_Food_Recipe_by_ID, scoreRecipe, BBC_Good_Food_API_Recipe_by_name_id, RecipeName2ID, GetIngredientsList, The_Mexican_Food_DB_List_of_Foods, The_Cocktail_DB_List_of_Cocktails, The_Vegan_Recipes_DB_List_of_Foods, Recipe_Details, Generate_recipe, addTaco, parseIngredients, CheckPantry, Get_Recipe, GroceryList, Recipe_Finder_cake_ingredient, get-recipe-ingredients, get_recipe_by_id, Generate_Recipe, Get_Recipe_by_ID, Get_Tips_for_Recipe, Worldwide_Recipes_Search, Recipe_v3_foodrecipe, drink_by_id, Get_a_Random_Low-Carb_Recipe, appetizer_ingredient, lunch_ingredient, Get_Food_Recipe_by_ID, Worldwide_Recipes_Detail, The_Vegan_Recipes_DB_Detailed_Food_Recipe_by_ID, Low_Carb_Recipes_Get_a_Random_Recipe, detailed_cocktail_recipe_by_id, Keto_Diet_Single_Keto_Recipe, Recetas_en_espa_ol_Get_recipes_details, Low_Carb_Recipes_Get_recipe_by_ID, The_Mexican_Food_DB_Detailed_Food_Recipe_by_ID, detailed_food_recipe_by_id

```
<tool_call>
{"name": "Get_Detailed_Cake_Recipe_by_ID", "arguments": {"type": "string", "properties": "string", "required": "cake789"}}
</tool_call>
<tool_call>
{"name": "side_dish_ingredient", "arguments": {"ingredient": "onions"}}
</tool_call>
```

### keyword search

Menu: Get_Side_Dish_Recipe, Get_Detailed_Cake_Recipe_by_ID, detailed_cake_recipe_by_id, FindRecipe, The_Birthday_Cake_DB_Detailed_Cake_Recipe_by_ID, side_dish_ingredient, cake_ingredient, The_Birthday_Cake_DB_List_of_Cakes, Recipe_Detail, Get_Cake_Recipe_by_Ingredient

```
<tool_call>
{"name": "Get_Detailed_Cake_Recipe_by_ID", "arguments": {"type": "string", "properties": "string", "required": "cake789"}}
</tool_call>
<tool_call>
{"name": "side_dish_ingredient", "arguments": {"ingredient": "onions"}}
</tool_call>
```

### original Open-Jev-2B top 10

Menu: Get_Recipe_by_ID, Get_Food_Recipe_by_ID, Get_Detailed_Cake_Recipe_by_ID, detailed_cake_recipe_by_id, The_Birthday_Cake_DB_List_of_Cakes, Recipe_Finder_side_dish_ingredient, Recipe_Details, The_Birthday_Cake_DB_Detailed_Cake_Recipe_by_ID, Recipe_Finder_cake_ingredient, Get_Recipe_Details

```
<tool_call>
{"name": "The_Birthday_Cake_DB_Detailed_Cake_Recipe_by_ID", "arguments": {"is_id": "cake789"}}
</tool_call>
<tool_call>
{"name": "Recipe_Finder_side_dish_ingredient", "arguments": {"ingredient": "onions"}}
</tool_call>
```

### tuned 2B top 10

Menu: side_dish_ingredient, Get_Side_Dish_Recipe, Recipe_Finder_side_dish_ingredient, Get_Detailed_Cake_Recipe_by_ID, detailed_cake_recipe_by_id, The_Birthday_Cake_DB_Detailed_Cake_Recipe_by_ID, The_Birthday_Cake_DB_List_of_Cakes, lunch_ingredient, appetizer_ingredient, Get_Recipe

```
<tool_call>
{"name": "detailed_cake_recipe_by_id", "arguments": {"is_id": "cake789"}}
</tool_call>
<tool_call>
{"name": "side_dish_ingredient", "arguments": {"ingredient": "onions"}}
</tool_call>
```

### hosted Jev top 10

Top 10: Get_Detailed_Cake_Recipe_by_ID, detailed_cake_recipe_by_id, Generate_Recipe, The_Birthday_Cake_DB_Detailed_Cake_Recipe_by_ID, side_dish_ingredient, Generate_recipe, Recipe_Detail, Recipe_Finder_side_dish_ingredient, Recipe_Details, Get_Side_Dish_Recipe

## train_49453

List cities in Italy and Spain with the keyword 'Rome'.

| Arm | Tools shown | Called | Matched full menu | Seconds |
| --- | ---: | --- | --- | ---: |
| full menu | 50 | SearchCities | yes | 3.41 |
| keyword search | 10 | Get_Cities_by_State_and_Keyword | no | 2.75 |
| original Open-Jev-2B top 10 | 10 | SearchCities | yes | 2.75 |
| tuned 2B top 10 | 10 | SearchCities | yes | 2.36 |
| hosted Jev top 10 | 10 | SearchCities | yes | 0.12 |

### full menu

Menu: Idealista_v2_properties_list, Beers_List_Get_beers_by_single_country, Get_Cities_by_State_and_Keyword, Get_Provinces_of_Spain, Get_beers_by_single_country, getRegions, cities, Get_All_Genres_for_Art_Openings_in_Italy, Get_Beers_by_Country, Get_Art_Openings_in_Italy, Spain_Songs_API, Spain_Songs, Italy_COVID-19_Statistics, SearchCities, GetTeams, Italy_Scheduled_Flights_Growth_API, Get_Cities_List, Get_German_Cities, Italy_Scheduled_Flights_Level, listLocations, Flixbus_cities, Cities_API, Spain_Scheduled_Flights_Growth_API, Get_All_Cities, Retrieve_Cities_by_State, Get_Cities_by_State, cities_2, Spain_Scheduled_Flights_Level_API, Priceline_com_Provider_Download_cities, weather_forecast_14_days_List_of_cities_in_one_C, GeoSource_API_cities_By_State, Referential_DB_Cities_in_a_state, Referential_DB_Cities_in_a_country, climate_data_List_of_cities_in_one_Country, Live_Events, Get_Cities_by_Homicide_Rate, Get_Cities_in_a_State, Get_Autonomous_Communities, getcompetitionsid, Get_Municipalities_by_Province, Billboard_API_Spain_Songs, Cities_Cost_of_Living_Get_Cities_List, Priceline_com_Provider_Download_cities_clusters, Get_Cities_by_Postcode, Get_Cities, Get_the_cities, Search_By_Keyword_Filters, Global_Flight_Data_Italy_Scheduled_Flights_Growt, Provinces_by_Autonomous_Community, get_cities

```
<tool_call>
{"name": "SearchCities", "arguments": {"keyword": "Rome", "country": "IT,ES"}}
</tool_call>
```

### keyword search

Menu: Idealista_v2_properties_list, Beers_List_Get_beers_by_single_country, Get_Cities_by_State_and_Keyword, Get_Provinces_of_Spain, Get_beers_by_single_country, getRegions, cities, Get_All_Genres_for_Art_Openings_in_Italy, Get_Beers_by_Country, Get_Art_Openings_in_Italy

```
<tool_call>
{"name": "Get_Cities_by_State_and_Keyword", "arguments": {"type": "Italy", "properties": "Rome", "required": "Rome"}}
</tool_call>
```

### original Open-Jev-2B top 10

Menu: SearchCities, Referential_DB_Cities_in_a_country, Cities_API, Get_Cities, weather_forecast_14_days_List_of_cities_in_one_C, cities_2, Get_Cities_List, Get_All_Cities, get_cities, Get_the_cities

```
<tool_call>
{"name": "SearchCities", "arguments": {"type": "object", "properties": {"search_keyword": "Rome", "country_codes": "IT,ES"}}}
</tool_call>
```

### tuned 2B top 10

Menu: get_cities, Get_All_Cities, cities, Get_the_cities, Get_Cities, Get_Cities_by_State_and_Keyword, SearchCities, Cities_API, climate_data_List_of_cities_in_one_Country, weather_forecast_14_days_List_of_cities_in_one_C

```
<tool_call>
{"name": "SearchCities", "arguments": {"type": "string", "properties": "Rome", "required": "IT,ES"}}
</tool_call>
```

### hosted Jev top 10

Top 10: SearchCities, Cities_API, Idealista_v2_properties_list, Beers_List_Get_beers_by_single_country, Get_Cities_by_State_and_Keyword, Get_Provinces_of_Spain, Get_beers_by_single_country, getRegions, cities, Get_All_Genres_for_Art_Openings_in_Italy

## train_45054

I'm organizing a themed party and I want to incorporate drinking challenges. Can you give me a random dirty challenge and a random sport challenge? We want to create a memorable and engaging experience for our guests!

| Arm | Tools shown | Called | Matched full menu | Seconds |
| --- | ---: | --- | --- | ---: |
| full menu | 50 | Drinking_Get_random_challange, Get_Random_Challenge | yes | 4.62 |
| keyword search | 10 | get_random_challange, Get_Random_Challenge | no | 3.04 |
| original Open-Jev-2B top 10 | 10 | Drinking_Get_random_challange, Drinking_Get_random_challange | yes | 3.24 |
| tuned 2B top 10 | 10 | Drinking_Get_random_challange, Get_Challenge_Data | yes | 2.98 |
| hosted Jev top 10 | 10 | Drinking_Get_random_challange | yes | 0.14 |

### full menu

Menu: Drinking_Get_random_challange, Get_Random_Question, Get_Random_Challenge, get_random_challange, Drinking_Get_random_question, Semantic_Quotes_Random_Quote, get_random_question, Get_Challenge_Data, TikTok_v3_Challenge_Videos, Get_Challenge_Videos, AG_Amazon_Data_Web_Scraper_Get_Amazon_Search_Res, TikTok_v4_Hashtag_Challenge_Info, Hashtag_Challenge_Posts, challenge, Get_Challenge, Google_Reviews_Scraper_SearchBusiness, Get_1P_Challenge_Tracking, Get_Challenge_Posts, TikTok_v3_Challenge, TikTok_Video_No_Watermark_v2_Search_challenge, ScrapTik_Challenge_Posts, Challenge_Posts, Get_Awemes_By_Challenge_ID, TikTok_Private_Challenge_Posts, TikTok_Private_Get_Awemes_By_Challenge_ID, TikTok_Scraper_v2_Hashtag_videos, TikTok_Scraper_v2_Hashtag_info, Get_TikTok_Video_Challenge_Information, Assess_the_Image_Quality, Chain49_Estimate_transaction_fee_V2, Image_QR_code_generator_Red_colour_QR_code_gener, GoogleSearch_serper_search, Bidirectional_Text_Language_Translation_Detect_L, Ebay_Search_Result_Search_on_ebay, analyze_recipe, aPalycg_reciZe, ViperScore_Get_managers, Valid_Whatsapp_Check_phone_number, Search_on_ebay, recash_Search, Magical_Taske_Fetch_by_type_and_region, USPTO_Trademark_v1_ownerSearch, League_Of_Legends_Esports_Get_Tournaments_For_Le, Airports_Info_Airport_Info, Tomba_EmailCount, Email_Checker_and_Validator_Check_Email, Tank01_Fantasy_Stats_Get_Player_Information, Tank01_NFL_Live_In_Game_Real_Time_Statistics_NFL, Cartify_getProductByName, ViperScore_Get_game_highlights

```
<tool_call>
{"name": "Drinking_Get_random_challange", "arguments": {"type": "dirty"}}
</tool_call>
<tool_call>
{"name": "Get_Random_Challenge", "arguments": {"type": "sport"}}
</tool_call>
```

### keyword search

Menu: Drinking_Get_random_challange, Get_Random_Question, Get_Random_Challenge, get_random_challange, Drinking_Get_random_question, Semantic_Quotes_Random_Quote, get_random_question, Get_Challenge_Data, TikTok_v3_Challenge_Videos, Get_Challenge_Videos

```
<tool_call>
{"name": "get_random_challange", "arguments": {"type": "dirty"}}
</tool_call>
<tool_call>
{"name": "Get_Random_Challenge", "arguments": {"type": "sport"}}
</tool_call>
```

### original Open-Jev-2B top 10

Menu: Get_Random_Challenge, get_random_challange, Drinking_Get_random_challange, Get_Challenge_Data, Drinking_Get_random_question, Get_Challenge, Get_Challenge_Posts, Get_Challenge_Videos, get_random_question, Magical_Taske_Fetch_by_type_and_region

```
<tool_call>
{"name": "Drinking_Get_random_challange", "arguments": {"type": "dirty"}}
</tool_call>
<tool_call>
{"name": "Drinking_Get_random_challange", "arguments": {"type": "sport"}}
</tool_call>
```

### tuned 2B top 10

Menu: Get_Random_Challenge, Drinking_Get_random_challange, get_random_challange, Get_Challenge_Data, Get_Challenge, GoogleSearch_serper_search, Get_Random_Question, get_random_question, Drinking_Get_random_question, challenge

```
<tool_call>
{"name": "Drinking_Get_random_challange", "arguments": {"type": "dirty"}}
</tool_call>
<tool_call>
{"name": "Get_Challenge_Data", "arguments": {"type": "sport"}}
</tool_call>
```

### hosted Jev top 10

Top 10: Drinking_Get_random_challange, Get_Random_Challenge, get_random_challange, Get_Challenge_Data, Get_Random_Question, Drinking_Get_random_question, Semantic_Quotes_Random_Quote, get_random_question, TikTok_v3_Challenge_Videos, Get_Challenge_Videos

## train_151414

Calculate the batting average of a baseball player who has had 500 hits and 1000 at-bats. Round the average to 2 decimal places.

| Arm | Tools shown | Called | Matched full menu | Seconds |
| --- | ---: | --- | --- | ---: |
| full menu | 50 | batting_average | yes | 4.41 |
| keyword search | 10 | batting_average | yes | 2.76 |
| original Open-Jev-2B top 10 | 10 | batting_average | yes | 2.77 |
| tuned 2B top 10 | 10 | batting_average | yes | 2.88 |
| hosted Jev top 10 | 10 | batting_average | yes | 0.13 |

### full menu

Menu: batting_average, Twelve_Data_AVG, players_get-batting, Twelve_Data_EMA, AverageReview, AverageRating, ReviewAverage, Cities_Cost_of_Living_and_Average_Prices_API_Cos, Twelve_Data_VWAP, calculate_required_sale, getGraphClusteringCoefficient, round_to_two_decimal_places, calculateInverterPower, getSentenceLength, Twelve_Data_MACD, Baseball_Player_Image, calculate_average_speed_round_trip_distance_one_, Greatest_of_All_Time_Billboard_200_Artists, Baseball_Player_Statistics_Seasons, Hull_Moving_Average, VWAP, Twelve_Data_TRIMA, aviation_emergency_response_time, Get_Current_Average_Price, calculate_weight_sum, Moving_Average_MA, get_decimal_places, Twelve_Data_KAMA, Get_Annual_Average_Dividend_Yield, Get_Baseball_Player_Regular_Season_Statistics, Hryvna_Today_v1_rates_today, Crypto_Markets_Current_Average_Price, Hryvna_Today_v1_rates_averages, find_median_of_consecutive_numbers_total_sum_num, Historical_Average_Salaries, Average_True_Range_ATR, calculate_teacher_weight, BaseballApi_PlayerStatisticsSeasons, BaseballApi_PlayerNearMatches, Qvantana_Hull_Moving_Average, Adzuna_Average_salary, calculate_average_adult_age, round_to_two_decimals, round_decimal, Get_Decimals, mental_multiplication_num1_num2, Get_Annual_Average_Dividend_Rate, calculate_factor_for_target_average_first_event_, Get_Drivers_by_Round_and_Year, find_lesser_of_two_numbers_sum_of_numbers_differ

```
<tool_call>
{"name": "batting_average", "arguments": {"num_hits": "500", "num_at_bats": "1000", "precision": "2"}}
</tool_call>
```

### keyword search

Menu: batting_average, Twelve_Data_AVG, players_get-batting, Twelve_Data_EMA, AverageReview, AverageRating, ReviewAverage, Cities_Cost_of_Living_and_Average_Prices_API_Cos, Twelve_Data_VWAP, calculate_required_sale

```
<tool_call>
{"name": "batting_average", "arguments": {"num_hits": "500", "num_at_bats": "1000", "precision": "2"}}
</tool_call>
```

### original Open-Jev-2B top 10

Menu: batting_average, round_to_two_decimal_places, round_to_two_decimals, players_get-batting, Get_Baseball_Player_Regular_Season_Statistics, round_decimal, get_decimal_places, Baseball_Player_Statistics_Seasons, BaseballApi_PlayerStatisticsSeasons, Hryvna_Today_v1_rates_averages

```
<tool_call>
{"name": "batting_average", "arguments": {"num_hits": "500", "num_at_bats": "1000", "precision": "2"}}
</tool_call>
```

### tuned 2B top 10

Menu: batting_average, round_to_two_decimals, round_to_two_decimal_places, round_decimal, players_get-batting, Greatest_of_All_Time_Billboard_200_Artists, calculate_average_speed_round_trip_distance_one_, Get_Decimals, get_decimal_places, Get_Drivers_by_Round_and_Year

```
<tool_call>
{"name": "batting_average", "arguments": {"num_hits": "500", "num_at_bats": "1000", "precision": "2"}}
</tool_call>
```

### hosted Jev top 10

Top 10: batting_average, Twelve_Data_AVG, players_get-batting, Twelve_Data_EMA, AverageReview, AverageRating, ReviewAverage, Cities_Cost_of_Living_and_Average_Prices_API_Cos, Twelve_Data_VWAP, calculate_required_sale
