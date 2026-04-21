#!/usr/bin/env python
# coding: utf-8

# In[8]:


print(2)
1


# In[1]:


1


# In[9]:


from futu import *
quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)

ret, data = quote_ctx.get_plate_list(Market.HK, Plate.ALL)
# if ret == RET_OK:
#     pass
#     # print(data)
#     # print(data['plate_name'][0]) # Take the first plate name
#     # print(data['plate_name'].values.tolist()) # Convert to list
# else:
#     print('error:', data)
# quote_ctx.close() # After using the connection, remember to close it to prevent the number of connections from running out


# In[ ]:





# In[2]:


data


# In[3]:


from futu import *
quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)



ret, data = quote_ctx.get_plate_stock('HK.BK1001') # 10 request per 30 seconds
if ret == RET_OK:
    print(data)
    print(data['stock_name'][0]) # Take the first stock name
    print(data['stock_name'].values.tolist()) # Convert to list
else:
    print('error:', data)
quote_ctx.close() # After using the connection, remember to close it to prevent the number of connections from running out


# In[4]:


from futu import *

quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)  # Create quote object
a=quote_ctx.get_market_snapshot('HK.00700')  # Get market snapshot for HK.00700
# quote_ctx.close() # Close object to prevent the number of connextions from running out


# In[6]:


a[1]


# In[ ]:


quote_ctx.get_market_snapshot('HK.00700')    
# Request up to 60 snapshots every 30 seconds
# For each request, the maximum number of stock codes supported by the parameter code_list is 400.
# Under the authority of Hong Kong stock BMP, the maximum number of snapshots of Hong Kong securities (including warrants, CBBC, and Inline Warrants) for a single request is 20
# Under the authority of Hong Kong futures and options BMP, the maximum number of snapshots of Hong Kong futures and options for a single request is 20


# In[ ]:


trd_ctx = OpenSecTradeContext(host='127.0.0.1', port=11111)  # Create trade object
print(trd_ctx.place_order(price=500.0, qty=100, code="HK.00700", trd_side=TrdSide.BUY, trd_env=TrdEnv.SIMULATE))  # Placing an order through paper trading account (It is nessary to unlock trade by trading password for placing orders in the real environment.)

trd_ctx.close()  # Close object to prevent the number of connextions from running out


