import csv
import io
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING

import requests
import streamlit as st

API = 'https://api.elections.kalshi.com/trade-api/v2'
BANKROLL = Decimal('50.00')
MAX_POSITION = Decimal('2.50')
MAX_EXPOSURE = Decimal('5.00')
MAX_SPREAD = Decimal('0.08')
MIN_VOLUME = Decimal('1')
MAX_QUOTE_AGE_SECONDS = 60

st.set_page_config(page_title='JARVIS Kalshi 006', page_icon='🛡️', layout='centered')
st.title('🛡️ JARVIS Kalshi 006')
st.caption('Sports → Crypto → Economics • Weather deferred • Read-only • No trading credentials')
st.metric('Paper bankroll', '$50.00')
st.warning('RESEARCH ONLY. No independent probability model, validated executable depth, or verified market-specific fee schedule. Every market is PASS.')

@st.cache_data(ttl=30, show_spinner=False)
def load_markets(pages):
    session = requests.Session()
    cursor = None
    seen = set()
    out = []
    for _ in range(pages):
        params = {'status': 'open', 'mve_filter': 'exclude', 'limit': 200}
        if cursor:
            params['cursor'] = cursor
        response = session.get(API + '/markets', params=params, timeout=15, headers={'Accept':'application/json'})
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get('markets'), list):
            raise ValueError('Malformed markets response')
        for market in data['markets']:
            ticker = market.get('ticker')
            if ticker and ticker not in seen:
                seen.add(ticker)
                out.append(market)
        new_cursor = data.get('cursor')
        if not new_cursor or new_cursor == cursor:
            break
        cursor = new_cursor
    return out

def dec(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None

def quote(m, key):
    value = dec(m.get(key))
    return value if value is not None and Decimal('0') < value < Decimal('1') else None

def general_fee(price, contracts=1):
    return (Decimal('0.07') * contracts * price * (1-price)).quantize(Decimal('0.01'), rounding=ROUND_CEILING)

def category(m):
    t = str(m.get('ticker','')).upper()
    title = str(m.get('title','')).lower()
    if re.search(r'^(KX(NBA|NFL|MLB|NHL|WTA|ATP|UFC|SOCCER|AFCON|NCA|F1|PGA|ITF))',t) or any(x in title for x in (' wins set ', ' receiving yards',' receptions',' touchdowns',' wins by more than')):
        return 'Sports'
    if any(x in t for x in ('BTC','ETH','SOL','CRYPTO','BITCOIN')) or any(x in title for x in ('bitcoin','ethereum','solana')):
        return 'Crypto'
    if any(x in t for x in ('CPI','FED','GDP','UNEMP','JOBS','INFLATION','RATE')) or any(x in title for x in ('federal reserve','inflation rate','unemployment rate','gross domestic product')):
        return 'Economics'
    if any(x in t for x in ('TEMP','WEATHER','RAIN','SNOW')):
        return 'Weather'
    return 'Other / unclassified'

def evaluate(m, scan_time):
    reasons=[]
    ask=quote(m,'yes_ask_dollars')
    bid=quote(m,'yes_bid_dollars')
    if ask is None or bid is None:
        reasons.append('missing valid bid/ask')
    elif bid > ask:
        reasons.append('crossed quote')
    elif ask-bid > MAX_SPREAD:
        reasons.append('spread exceeds 8¢')
    volume=dec(m.get('volume_fp',m.get('volume',0)))
    if volume is None or volume < MIN_VOLUME:
        reasons.append('missing or zero reported volume')
    if m.get('status') not in ('active','open'):
        reasons.append('not open')
    if m.get('mve_collection_ticker') or m.get('is_multivariate') is True:
        reasons.append('multivariate')
    if ask is not None and ask+general_fee(ask)>MAX_POSITION:
        reasons.append('one-contract cost exceeds $2.50 risk cap')
    # No quote-level timestamp or depth validated: never infer freshness from scan timestamp.
    reasons.extend(['quote freshness unverified', 'executable depth unverified', 'independent probability unavailable', 'fee schedule unverified', 'settlement rules not reviewed'])
    return {'ticker':str(m.get('ticker','')), 'title':str(m.get('title','')),
            'category':category(m), 'yes_ask':ask, 'yes_bid':bid, 'volume':volume,
            'fee_estimate':general_fee(ask) if ask is not None else None,
            'break_even_estimate':ask+general_fee(ask) if ask is not None else None,
            'reasons':reasons, 'status':'PASS', 'scan_utc':scan_time}

pages=st.slider('Market pages (200 each)',1,15,5)
if st.button('🔄 Refresh live markets', type='primary', use_container_width=True):
    load_markets.clear()
try:
    with st.spinner('Fetching live public Kalshi markets...'):
        markets=load_markets(pages)
except (requests.RequestException,ValueError) as exc:
    st.error('Live market request failed. No cached quotes are substituted: '+str(exc)[:220])
    st.stop()
scan_time=datetime.now(timezone.utc).isoformat(timespec='seconds')
results=[evaluate(m,scan_time) for m in markets]
st.success(f'Fetched {len(results)} unique markets · {scan_time}')
st.caption('Pagination covers a sample of open markets, not necessarily every market or category.')
selection=st.multiselect('Focus categories', ['Sports','Crypto','Economics','Weather','Other / unclassified'],default=['Sports','Crypto','Economics'])
search=st.text_input('Search market title or ticker')
selected=[r for r in results if r['category'] in selection and search.lower() in (r['ticker']+' '+r['title']).lower()]
counts={c:sum(r['category']==c for r in results) for c in ['Sports','Crypto','Economics','Weather','Other / unclassified']}
st.write('Sample category counts: '+ ' · '.join(f'{k}: {v}' for k,v in counts.items()))
st.metric('Verified positive edges',0)
st.caption('The category classifier is heuristic. Review event metadata and contract rules before relying on classifications.')

# Candidate shortlist is for inspection, never a trade recommendation.
selected.sort(key=lambda r: (len(r['reasons']), -(r['volume'] or Decimal(0))))
for r in selected[:30]:
    ask='N/A' if r['yes_ask'] is None else f'${r["yes_ask"]:.2f}'
    with st.expander(f'PASS · {r["category"]} · {ask} · {r["title"][:70]}'):
        st.write(r['ticker'])
        st.write(r['title'])
        st.write(f'YES ask: {ask} · YES bid: {r["yes_bid"] if r["yes_bid"] is not None else "N/A"} · Reported volume: {r["volume"]}')
        if r['fee_estimate'] is not None:
            st.write(f'General taker-fee estimate for 1 YES: ${r["fee_estimate"]:.2f} · indicative break-even: {r["break_even_estimate"]*100:.1f}%')
        st.write('Reasons for PASS: '+ '; '.join(r['reasons']))
        st.caption('This is an indicative quote, not verified fillable order-book liquidity.')

st.divider()
st.subheader('Risk controls')
st.write('Paper bankroll: $50 · Max risk/position: $2.50 · Max aggregate exposure: $5.00 · Max displayed spread: 8¢ · Max permitted verified quote age: 60 seconds.')
st.write('No trade signal is permitted until timestamped executable order-book depth, exact contract rules, market-specific fees, and independently validated probability estimates are all available. The current app intentionally issues no signals.')
st.write('The general fee is an estimate only. Market-specific schedules, rounding, slippage, and any exit fees must be verified before treating a contract as positive EV.')

buf=io.StringIO()
writer=csv.writer(buf)
writer.writerow(['scan_utc','ticker','category','title','yes_ask_dollars','yes_bid_dollars','reported_volume','estimated_fee_1','indicative_break_even','status','rejection_reasons'])
for r in selected:
    writer.writerow([r['scan_utc'],r['ticker'],r['category'],r['title'],r['yes_ask'],r['yes_bid'],r['volume'],r['fee_estimate'],r['break_even_estimate'],r['status'],'; '.join(r['reasons'])])
st.download_button('⬇️ Export scan audit CSV',data=buf.getvalue(),file_name='jarvis_scan_audit.csv',mime='text/csv',use_container_width=True)
st.caption('Read-only; no order placement, no Kalshi credentials, no persistent paper-trade ledger, and no background monitoring. CSV export is manual.')
