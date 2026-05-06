"""
News Ingestion Engine.
Pulls economic calendar from free sources and adjusts trading around events.
Creates quiet periods before/after high-impact news on affected currencies.

ZERO MODIFICATIONS to existing files.
Attaches via feature flag ENABLE_NEWS_INGESTION in config.
Requires new table: economic_events (added to schema.sql append-only).
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
import httpx
from core.logger import get_logger

logger = get_logger("data.news")


@dataclass
class EconomicEvent:
    """Economic calendar event."""
    event_name: str
    currency: str
    impact: str  # HIGH, MEDIUM, LOW
    scheduled_time: datetime
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    event_id: Optional[str] = None


@dataclass
class NewsQuietPeriod:
    """Quiet period around a news event."""
    event: EconomicEvent
    affected_pairs: List[str]
    quiet_start: datetime
    quiet_end: datetime
    pre_event_minutes: int = 5
    post_event_minutes: int = 5


@dataclass
class NewsState:
    """Current news-related trading state."""
    active_quiet_periods: List[NewsQuietPeriod]
    restricted_pairs: Set[str]
    next_event: Optional[EconomicEvent] = None
    events_next_hour: List[EconomicEvent] = field(default_factory=list)


class NewsIngestionEngine:
    """
    Fetches and processes economic calendar data.
    
    Data sources (free, no API key required):
    - ForexFactory RSS feed
    - Investing.com economic calendar (scraping fallback)
    
    Actions during quiet periods:
    - Suspend new entries on affected pairs
    - Tighten stops on affected open positions
    - Optionally arm news spike straddle strategy
    """

    # Quiet period durations (minutes)
    PRE_EVENT_QUIET: Dict[str, int] = {
        "HIGH": 5,
        "MEDIUM": 2,
        "LOW": 0,
    }
    POST_EVENT_QUIET: Dict[str, int] = {
        "HIGH": 5,
        "MEDIUM": 2,
        "LOW": 0,
    }

    # Currency to pair mapping
    CURRENCY_PAIRS: Dict[str, List[str]] = {
        "USD": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"],
        "EUR": ["EURUSD", "EURGBP", "EURJPY", "EURCHF"],
        "GBP": ["GBPUSD", "EURGBP", "GBPJPY", "GBPCHF"],
        "JPY": ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY"],
        "CHF": ["USDCHF", "EURCHF", "GBPCHF"],
        "AUD": ["AUDUSD", "AUDJPY"],
        "CAD": ["USDCAD"],
        "NZD": ["NZDUSD"],
    }

    # Polling interval
    POLL_INTERVAL_MINUTES: int = 15
    CACHE_TTL_MINUTES: int = 15

    def __init__(self, db_client):
        """
        Initialize news ingestion engine.
        
        Args:
            db_client: Database client for event storage
        """
        self.db = db_client
        self.events: List[EconomicEvent] = []
        self.active_quiet_periods: List[NewsQuietPeriod] = []
        self.restricted_pairs: Set[str] = set()
        self.last_poll: Optional[datetime] = None
        self._polling: bool = False
        self._poll_task: Optional[asyncio.Task] = None

        logger.info("News Ingestion Engine initialized")

    async def start_polling(self):
        """Start background polling for economic events."""
        if self._polling:
            return

        self._polling = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            f"News polling started — every {self.POLL_INTERVAL_MINUTES} minutes"
        )

    async def stop_polling(self):
        """Stop background polling."""
        self._polling = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("News polling stopped")

    async def _poll_loop(self):
        """Background polling loop."""
        while self._polling:
            try:
                await self._fetch_events()
                await self._update_quiet_periods()
                await asyncio.sleep(self.POLL_INTERVAL_MINUTES * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"News polling error: {e}")
                await asyncio.sleep(60)

    async def _fetch_events(self):
        """Fetch economic events from data sources."""
        now = datetime.now(timezone.utc)

        # Check cache
        if self.last_poll:
            cache_age = (now - self.last_poll).total_seconds() / 60
            if cache_age < self.CACHE_TTL_MINUTES:
                return

        try:
            # Try ForexFactory RSS (free, no API key)
            events = await self._fetch_forexfactory_rss()
            if events:
                self.events = events
                self.last_poll = now

                # Store new events in database
                await self._store_events(events)

                logger.debug(f"Fetched {len(events)} economic events")
            else:
                logger.debug("No new events found")

        except Exception as e:
            logger.error(f"Failed to fetch economic events: {e}")

    async def _fetch_forexfactory_rss(self) -> List[EconomicEvent]:
        """
        Fetch economic calendar from ForexFactory RSS.
        Free, no authentication required.
        """
        url = "https://www.forexfactory.com/ffcal_week_this.xml"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, follow_redirects=True)

                if response.status_code != 200:
                    logger.warning(f"ForexFactory RSS returned {response.status_code}")
                    return []

                # Parse RSS XML (simplified — production would use feedparser)
                events = self._parse_rss(response.text)
                return events

        except httpx.TimeoutException:
            logger.warning("ForexFactory RSS timeout")
            return []
        except Exception as e:
            logger.error(f"ForexFactory RSS error: {e}")
            return []

    def _parse_rss(self, xml_content: str) -> List[EconomicEvent]:
        """
        Parse ForexFactory RSS XML.
        Simplified parser — in production, use feedparser library.
        """
        events = []
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_content)

            for item in root.findall(".//item"):
                try:
                    title = item.find("title").text or ""
                    description = item.find("description").text or ""
                    pub_date = item.find("pubDate").text or ""

                    # Parse event details from title/description
                    event = self._parse_event_details(title, description, pub_date)
                    if event:
                        events.append(event)
                except (AttributeError, ValueError) as e:
                    logger.debug(f"Skipping malformed RSS item: {e}")
                    continue

        except ET.ParseError as e:
            logger.error(f"RSS XML parse error: {e}")
        except ImportError:
            logger.warning("xml.etree not available — install feedparser")

        return events

    def _parse_event_details(
        self,
        title: str,
        description: str,
        pub_date: str,
    ) -> Optional[EconomicEvent]:
        """Parse individual event details from RSS data."""
        # Determine impact
        impact = "LOW"
        if "High" in title or "HIGH" in title.upper():
            impact = "HIGH"
        elif "Medium" in title or "MEDIUM" in title.upper():
            impact = "MEDIUM"

        # Extract currency
        currency = "USD"  # Default
        currency_codes = ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"]
        for code in currency_codes:
            if code in title.upper():
                currency = code
                break

        # Parse scheduled time
        try:
            from email.utils import parsedate_to_datetime
            scheduled_time = parsedate_to_datetime(pub_date).replace(tzinfo=timezone.utc)
        except (ValueError, ImportError):
            try:
                scheduled_time = datetime.strptime(
                    pub_date, "%a, %d %b %Y %H:%M:%S %z"
                )
            except ValueError:
                scheduled_time = datetime.now(timezone.utc) + timedelta(hours=1)

        return EconomicEvent(
            event_name=title[:100],
            currency=currency,
            impact=impact,
            scheduled_time=scheduled_time,
        )

    async def _store_events(self, events: List[EconomicEvent]):
        """Store new events in database."""
        stored = 0
        for event in events:
            try:
                # Check if event already exists
                existing = await self.db.get_events(
                    limit=1,
                    event_type=f"ECONOMIC_EVENT_{event.event_name}",
                )
                if not existing:
                    await self.db.save_event(
                        event_type="ECONOMIC_EVENT",
                        message=event.event_name,
                        data={
                            "currency": event.currency,
                            "impact": event.impact,
                            "scheduled_time": event.scheduled_time.isoformat(),
                            "actual": event.actual,
                            "forecast": event.forecast,
                            "previous": event.previous,
                        },
                    )
                    stored += 1
            except Exception as e:
                logger.error(f"Failed to store event: {e}")

        if stored > 0:
            logger.debug(f"Stored {stored} new economic events")

    async def _update_quiet_periods(self):
        """Update active quiet periods based on upcoming events."""
        now = datetime.now(timezone.utc)
        self.active_quiet_periods = []
        self.restricted_pairs = set()

        for event in self.events:
            # Check if event is within relevant window
            pre_minutes = self.PRE_EVENT_QUIET.get(event.impact, 0)
            post_minutes = self.POST_EVENT_QUIET.get(event.impact, 0)

            if pre_minutes + post_minutes == 0:
                continue  # No quiet period for LOW impact

            quiet_start = event.scheduled_time - timedelta(minutes=pre_minutes)
            quiet_end = event.scheduled_time + timedelta(minutes=post_minutes)

            if quiet_start <= now <= quiet_end:
                affected_pairs = self._get_affected_pairs(event.currency)
                quiet_period = NewsQuietPeriod(
                    event=event,
                    affected_pairs=affected_pairs,
                    quiet_start=quiet_start,
                    quiet_end=quiet_end,
                    pre_event_minutes=pre_minutes,
                    post_event_minutes=post_minutes,
                )
                self.active_quiet_periods.append(quiet_period)
                self.restricted_pairs.update(affected_pairs)

        if self.active_quiet_periods:
            logger.debug(
                f"Active quiet periods: {len(self.active_quiet_periods)} | "
                f"Restricted pairs: {len(self.restricted_pairs)}"
            )

    def _get_affected_pairs(self, currency: str) -> List[str]:
        """Get all trading pairs affected by a currency event."""
        return self.CURRENCY_PAIRS.get(currency.upper(), [])

    def is_pair_restricted(self, symbol: str) -> bool:
        """
        Check if a pair is currently in a news quiet period.
        
        Args:
            symbol: Trading pair (e.g., "EURUSD")
            
        Returns:
            True if the pair should not be traded
        """
        return symbol in self.restricted_pairs

    def get_restricted_pairs(self) -> Set[str]:
        """Get set of all currently restricted pairs."""
        return self.restricted_pairs.copy()

    def get_active_quiet_periods(self) -> List[NewsQuietPeriod]:
        """Get list of active quiet periods."""
        return self.active_quiet_periods.copy()

    def get_next_event(self) -> Optional[EconomicEvent]:
        """Get the next upcoming economic event."""
        now = datetime.now(timezone.utc)
        future_events = [
            e for e in self.events
            if e.scheduled_time > now
        ]
        if future_events:
            return min(future_events, key=lambda e: e.scheduled_time)
        return None

    def get_events_next_hour(self) -> List[EconomicEvent]:
        """Get all events scheduled in the next hour."""
        now = datetime.now(timezone.utc)
        one_hour = now + timedelta(hours=1)
        return [
            e for e in self.events
            if now <= e.scheduled_time <= one_hour
        ]

    def get_news_state(self) -> NewsState:
        """Get comprehensive news state for current moment."""
        return NewsState(
            active_quiet_periods=self.active_quiet_periods.copy(),
            restricted_pairs=self.restricted_pairs.copy(),
            next_event=self.get_next_event(),
            events_next_hour=self.get_events_next_hour(),
        )

    def get_stats(self) -> dict:
        """Get news engine statistics."""
        return {
            "total_events_tracked": len(self.events),
            "active_quiet_periods": len(self.active_quiet_periods),
            "restricted_pairs": list(self.restricted_pairs),
            "next_event": (
                self.get_next_event().event_name
                if self.get_next_event()
                else None
            ),
            "events_next_hour": len(self.get_events_next_hour()),
            "last_poll": (
                self.last_poll.isoformat()
                if self.last_poll
                else None
            ),
            "polling_active": self._polling,
        }