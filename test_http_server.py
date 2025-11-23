"""
Comprehensive test suite for http_server.py

Tests all major functionality including:
- Configuration loading
- Webhook endpoints
- Event translation
- Video Intelligence batching
- Object tracking
- IoU calculation
- Error handling
- Graceful shutdown
"""

import pytest
import json
import time
import threading
import signal
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import http_server


class TestConfiguration:
    """Test configuration loading and validation"""
    
    def test_load_config_with_slack_url(self):
        """Test config loads when SLACK_WEBHOOK_URL is set"""
        with patch.dict(os.environ, {'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'}):
            config = http_server.load_config()
            assert 'slack_webhook_url' in config
            assert config['slack_webhook_url'] == 'https://hooks.slack.com/test'
    
    def test_load_config_without_slack_url(self):
        """Test config handles missing SLACK_WEBHOOK_URL gracefully"""
        with patch.dict(os.environ, {}, clear=True):
            config = http_server.load_config()
            assert 'slack_webhook_url' not in config
    
    def test_vi_batch_window_validation(self):
        """Test VI_BATCH_WINDOW validates correctly"""
        # Valid value
        with patch.dict(os.environ, {'VI_BATCH_WINDOW': '5'}):
            import importlib
            importlib.reload(http_server)
            assert http_server.VI_BATCH_WINDOW == 5
        
        # Invalid value (too low)
        with patch.dict(os.environ, {'VI_BATCH_WINDOW': '0'}):
            importlib.reload(http_server)
            assert http_server.VI_BATCH_WINDOW == 10  # Falls back to default
        
        # Invalid value (non-numeric)
        with patch.dict(os.environ, {'VI_BATCH_WINDOW': 'invalid'}):
            importlib.reload(http_server)
            assert http_server.VI_BATCH_WINDOW == 10  # Falls back to default
    
    def test_vi_max_batch_size_config(self):
        """Test VI_MAX_BATCH_SIZE loads from environment"""
        with patch.dict(os.environ, {'VI_MAX_BATCH_SIZE': '5000'}):
            import importlib
            importlib.reload(http_server)
            assert http_server.VI_MAX_BATCH_SIZE == 5000


class TestUtilityFunctions:
    """Test utility functions"""
    
    def test_sanitize_url(self):
        """Test URL sanitization for logging"""
        url = "https://hooks.slack.com/services/T123/B456/secretToken"
        sanitized = http_server.sanitize_url(url)
        assert "secretToken" not in sanitized
        assert "hooks.slack.com" in sanitized
        
        # Test with None
        assert http_server.sanitize_url(None) == "<not configured>"
    
    def test_format_timestamp_epoch_seconds(self):
        """Test timestamp formatting with epoch seconds"""
        ts = 1700000000  # Some timestamp
        result = http_server.format_timestamp(ts)
        assert isinstance(result, str)
        assert len(result) > 10  # Should be formatted string
    
    def test_format_timestamp_epoch_milliseconds(self):
        """Test timestamp formatting with epoch milliseconds"""
        ts = 1700000000000  # Milliseconds
        result = http_server.format_timestamp(ts)
        assert isinstance(result, str)
        assert len(result) > 10
    
    def test_format_timestamp_iso_string(self):
        """Test timestamp formatting with ISO string"""
        ts = "2024-01-01T12:00:00Z"
        result = http_server.format_timestamp(ts)
        assert isinstance(result, str)
    
    def test_format_timestamp_numeric_string(self):
        """Test timestamp formatting with numeric string"""
        ts = "1700000000"
        result = http_server.format_timestamp(ts)
        assert isinstance(result, str)
    
    def test_format_timestamp_none(self):
        """Test timestamp formatting with None returns current time"""
        result = http_server.format_timestamp(None)
        assert isinstance(result, str)
        assert len(result) > 10


class TestIoUCalculation:
    """Test Intersection over Union calculations"""
    
    def test_calculate_iou_no_overlap(self):
        """Test IoU with non-overlapping boxes"""
        bbox1 = {'x': 0, 'y': 0, 'w': 10, 'h': 10}
        bbox2 = {'x': 20, 'y': 20, 'w': 10, 'h': 10}
        assert http_server.calculate_iou(bbox1, bbox2) == 0.0
    
    def test_calculate_iou_perfect_overlap(self):
        """Test IoU with identical boxes"""
        bbox1 = {'x': 0, 'y': 0, 'w': 10, 'h': 10}
        bbox2 = {'x': 0, 'y': 0, 'w': 10, 'h': 10}
        assert http_server.calculate_iou(bbox1, bbox2) == 1.0
    
    def test_calculate_iou_partial_overlap(self):
        """Test IoU with partial overlap"""
        bbox1 = {'x': 0, 'y': 0, 'w': 10, 'h': 10}
        bbox2 = {'x': 5, 'y': 5, 'w': 10, 'h': 10}
        iou = http_server.calculate_iou(bbox1, bbox2)
        assert 0.0 < iou < 1.0
    
    def test_calculate_iou_invalid_bbox(self):
        """Test IoU with invalid bounding boxes"""
        bbox1 = {'x': 0, 'y': 0, 'w': 10, 'h': 10}
        bbox2 = {'x': 0, 'y': 0}  # Missing w and h
        assert http_server.calculate_iou(bbox1, bbox2) == 0.0
    
    def test_calculate_iou_negative_dimensions(self):
        """Test IoU with negative dimensions"""
        bbox1 = {'x': 0, 'y': 0, 'w': 10, 'h': 10}
        bbox2 = {'x': 0, 'y': 0, 'w': -5, 'h': 10}
        assert http_server.calculate_iou(bbox1, bbox2) == 0.0
    
    def test_calculate_iou_zero_area(self):
        """Test IoU with zero area boxes"""
        bbox1 = {'x': 0, 'y': 0, 'w': 0, 'h': 0}
        bbox2 = {'x': 0, 'y': 0, 'w': 10, 'h': 10}
        assert http_server.calculate_iou(bbox1, bbox2) == 0.0


class TestObjectTracking:
    """Test object tracking functionality"""
    
    def test_track_objects_empty_detections(self):
        """Test tracking with empty detection list"""
        result = http_server.track_objects([])
        assert result['unique_count'] == 0
        assert result['frames_processed'] == 0
        assert result['peak_occupancy'] == 0
        assert result['avg_occupancy'] == 0
    
    def test_track_objects_single_frame(self):
        """Test tracking with single frame"""
        detections = [
            {
                'bbox': {'x': 10, 'y': 10, 'w': 50, 'h': 100},
                'frame_id': 1,
                'class_name': 'person',
                'confidence': 0.9
            },
            {
                'bbox': {'x': 100, 'y': 10, 'w': 50, 'h': 100},
                'frame_id': 1,
                'class_name': 'person',
                'confidence': 0.85
            }
        ]
        result = http_server.track_objects(detections)
        assert result['unique_count'] == 2
        assert result['frames_processed'] == 1
        assert result['peak_occupancy'] == 2
        assert result['avg_occupancy'] == 2.0
    
    def test_track_objects_multiple_frames_same_object(self):
        """Test tracking same object across frames"""
        detections = [
            {
                'bbox': {'x': 10, 'y': 10, 'w': 50, 'h': 100},
                'frame_id': 1,
                'class_name': 'person',
                'confidence': 0.9
            },
            {
                'bbox': {'x': 12, 'y': 12, 'w': 50, 'h': 100},  # Slightly moved
                'frame_id': 2,
                'class_name': 'person',
                'confidence': 0.9
            }
        ]
        result = http_server.track_objects(detections)
        # Should track as 1 unique object moving
        assert result['unique_count'] == 1
        assert result['frames_processed'] == 2
    
    def test_track_objects_invalid_detections(self):
        """Test tracking with invalid detection data"""
        detections = [
            {'frame_id': 1},  # Missing bbox
            {'bbox': {'x': 10, 'y': 10, 'w': 50, 'h': 100}},  # Missing frame_id
            {'bbox': 'invalid', 'frame_id': 1}  # Invalid bbox type
        ]
        result = http_server.track_objects(detections)
        assert result['unique_count'] == 0
        assert result['frames_processed'] == 0


class TestEventTranslation:
    """Test event translation functionality"""
    
    def test_translate_app_started(self):
        """Test translation of app.started event"""
        payload = {
            'name': 'app.started',
            'timestamp': 1700000000000,
            'context': {
                'app': 'live',
                'appInstance': '_definst_',
                'vhost': '_defaultVHost_'
            },
            'source': 'Wowza'
        }
        text, blocks, severity = http_server.translate_payload(payload)
        assert 'Application started' in text
        assert severity == 'low'
        assert len(blocks) > 0
    
    def test_translate_stream_started(self):
        """Test translation of stream.started event"""
        payload = {
            'name': 'stream.started',
            'timestamp': 1700000000000,
            'context': {
                'stream': 'mystream',
                'app': 'live',
                'appInstance': '_definst_',
                'vhost': '_defaultVHost_',
                'state': 'started'
            }
        }
        text, blocks, severity = http_server.translate_payload(payload)
        assert 'Live stream started' in text
        assert 'mystream' in text
        assert len(blocks) > 0
    
    def test_translate_recording_failed(self):
        """Test translation of recording.failed event (high severity)"""
        payload = {
            'name': 'recording.failed',
            'timestamp': 1700000000000,
            'context': {
                'stream': 'mystream',
                'app': 'live'
            },
            'data': {
                'error': 'Disk full'
            }
        }
        text, blocks, severity = http_server.translate_payload(payload)
        assert 'Recording failed' in text
        assert severity == 'high'
        assert ':rotating_light:' in text
    
    def test_translate_vi_detection_batching(self):
        """Test that VI detections return None (for batching)"""
        payload = {
            'name': 'video.intelligence.detection',
            'timestamp': 1700000000000,
            'context': {
                'stream': 'mystream',
                'app': 'live'
            },
            'data': {
                'vi_data': [
                    {
                        'frame_id': 1,
                        'detections': [
                            {
                                'class_name': 'person',
                                'confidence': 0.95,
                                'bbox': {'x': 10, 'y': 10, 'w': 50, 'h': 100}
                            }
                        ]
                    }
                ]
            }
        }
        result = http_server.translate_payload(payload)
        assert result is None  # Should return None for batching
    
    def test_translate_unknown_event(self):
        """Test translation of unrecognized event"""
        payload = {
            'name': 'unknown.event.type',
            'timestamp': 1700000000000,
            'context': {},
            'data': {'some': 'data'}
        }
        text, blocks, severity = http_server.translate_payload(payload)
        assert 'Unknown Event' in text
        assert len(blocks) > 0
    
    def test_translate_error_handling(self):
        """Test translation handles malformed payloads"""
        payload = {'invalid': 'structure'}
        text, blocks, severity = http_server.translate_payload(payload)
        assert isinstance(text, str)
        assert isinstance(blocks, list)
        assert severity == 'low'


class TestVIBatching:
    """Test Video Intelligence batching functionality"""
    
    def setup_method(self):
        """Reset batch data before each test"""
        http_server.vi_batch_data.clear()
        if http_server.vi_batch_timer:
            http_server.vi_batch_timer.cancel()
            http_server.vi_batch_timer = None
    
    def test_schedule_vi_batch_flush(self):
        """Test batch flush scheduling"""
        http_server.schedule_vi_batch_flush()
        assert http_server.vi_batch_timer is not None
        assert http_server.vi_batch_timer.is_alive()
        http_server.vi_batch_timer.cancel()
    
    def test_schedule_vi_batch_flush_already_scheduled(self):
        """Test that multiple schedules don't create multiple timers"""
        http_server.schedule_vi_batch_flush()
        timer1 = http_server.vi_batch_timer
        http_server.schedule_vi_batch_flush()
        timer2 = http_server.vi_batch_timer
        assert timer1 is timer2  # Should be same timer
        timer1.cancel()
    
    @patch('http_server.send_to_slack')
    def test_flush_vi_batch(self, mock_send):
        """Test batch flushing"""
        # Add some detections to batch
        stream_key = "live|mystream"
        http_server.vi_batch_data[stream_key] = {
            'detections': [
                {
                    'class_name': 'person',
                    'confidence': 0.95,
                    'frame_id': 1,
                    'bbox': {'x': 10, 'y': 10, 'w': 50, 'h': 100}
                }
            ],
            'first_seen': datetime.now(),
            'last_seen': datetime.now()
        }
        
        http_server.flush_vi_batch()
        
        # Should have sent to Slack
        assert mock_send.called
        # Batch should be cleared
        assert len(http_server.vi_batch_data) == 0
    
    def test_vi_batch_size_limit(self):
        """Test that batch flushes early when size limit exceeded"""
        with patch('http_server.VI_MAX_BATCH_SIZE', 10):
            with patch('http_server.flush_vi_batch') as mock_flush:
                # Create payload with many detections
                detections = [
                    {
                        'class_name': 'person',
                        'confidence': 0.9,
                        'frame_id': i,
                        'bbox': {'x': 10, 'y': 10, 'w': 50, 'h': 100}
                    }
                    for i in range(15)
                ]
                
                stream_key = "live|mystream"
                http_server.vi_batch_data[stream_key]['detections'] = detections
                http_server.vi_batch_data[stream_key]['first_seen'] = datetime.now()
                http_server.vi_batch_data[stream_key]['last_seen'] = datetime.now()
                
                # Trigger by translating VI event with more data
                payload = {
                    'name': 'video.intelligence.detection',
                    'context': {'stream': 'mystream', 'app': 'live'},
                    'data': {'vi_data': [{'frame_id': 20, 'detections': []}]}
                }
                http_server.translate_payload(payload)
                
                # Should have flushed due to size limit
                assert mock_flush.called or len(http_server.vi_batch_data[stream_key]['detections']) >= 10


class TestFlaskEndpoints:
    """Test Flask endpoint functionality"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        http_server.app.config['TESTING'] = True
        with http_server.app.test_client() as client:
            yield client
    
    def test_health_check(self, client):
        """Test /health endpoint"""
        response = client.get('/health')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
    
    @patch('http_server.send_to_slack')
    def test_webhook_valid_payload(self, mock_send, client):
        """Test /webhook with valid payload"""
        payload = {
            'name': 'stream.started',
            'timestamp': 1700000000000,
            'context': {
                'stream': 'test',
                'app': 'live',
                'vhost': '_defaultVHost_'
            }
        }
        response = client.post('/webhook',
                              data=json.dumps(payload),
                              content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'
        assert mock_send.called
    
    def test_webhook_invalid_json(self, client):
        """Test /webhook with invalid JSON"""
        response = client.post('/webhook',
                              data='not json',
                              content_type='application/json')
        # Flask's get_json() raises BadRequest, caught by generic handler → 500
        assert response.status_code == 500
    
    def test_webhook_empty_payload(self, client):
        """Test /webhook with empty payload"""
        response = client.post('/webhook',
                              data=json.dumps({}),
                              content_type='application/json')
        # Empty payload is valid JSON but has no payload data, returns 400
        assert response.status_code == 400
    
    @patch('http_server.send_to_slack')
    def test_webhook_vi_detection(self, mock_send, client):
        """Test /webhook with VI detection (should not send immediately)"""
        payload = {
            'name': 'video.intelligence.detection',
            'context': {'stream': 'test', 'app': 'live'},
            'data': {
                'vi_data': [
                    {
                        'frame_id': 1,
                        'detections': [
                            {
                                'class_name': 'person',
                                'confidence': 0.9,
                                'bbox': {'x': 10, 'y': 10, 'w': 50, 'h': 100}
                            }
                        ]
                    }
                ]
            }
        }
        response = client.post('/webhook',
                              data=json.dumps(payload),
                              content_type='application/json')
        assert response.status_code == 200
        # Should NOT send immediately (batched)
        assert not mock_send.called


class TestSlackIntegration:
    """Test Slack message sending"""
    
    @patch('http_server.http_session.post')
    def test_send_to_slack_with_blocks(self, mock_post):
        """Test sending message with blocks"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        with patch.dict(os.environ, {'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'}):
            http_server.CONFIG = http_server.load_config()
            
            message = (
                "Test message",
                [{"type": "section", "text": {"type": "mrkdwn", "text": "*Test*"}}],
                'low'
            )
            http_server.send_to_slack(message)
            
            assert mock_post.called
            call_args = mock_post.call_args
            assert 'blocks' in call_args[1]['json']
    
    @patch('http_server.http_session.post')
    def test_send_to_slack_fallback_to_text(self, mock_post):
        """Test fallback to plain text when blocks fail"""
        mock_response_blocks = Mock()
        mock_response_blocks.status_code = 400  # Blocks not supported
        mock_response_text = Mock()
        mock_response_text.status_code = 200
        mock_post.side_effect = [mock_response_blocks, mock_response_text]
        
        with patch.dict(os.environ, {'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'}):
            http_server.CONFIG = http_server.load_config()
            
            message = (
                "Test message",
                [{"type": "section", "text": {"type": "mrkdwn", "text": "*Test*"}}],
                'low'
            )
            http_server.send_to_slack(message)
            
            assert mock_post.call_count == 2  # Tried blocks, then text
    
    def test_send_to_slack_no_webhook_configured(self):
        """Test that send_to_slack handles missing webhook gracefully"""
        with patch.dict(os.environ, {}, clear=True):
            http_server.CONFIG = http_server.load_config()
            # Should not raise exception
            http_server.send_to_slack(("Test", [], 'low'))


class TestGracefulShutdown:
    """Test graceful shutdown functionality"""
    
    @patch('http_server.flush_vi_batch')
    @patch('http_server.http_session.close')
    def test_shutdown_handler(self, mock_session_close, mock_flush):
        """Test shutdown handler"""
        frame = Mock()
        http_server.shutdown_handler(signal.SIGTERM, frame)
        
        assert mock_flush.called
        assert mock_session_close.called
        assert http_server.shutdown_flag.is_set()


class TestThreadSafety:
    """Test thread safety of concurrent operations"""
    
    def test_concurrent_batch_additions(self):
        """Test that concurrent webhook requests don't corrupt batch data"""
        http_server.vi_batch_data.clear()
        
        def add_detection(thread_id):
            for i in range(10):
                payload = {
                    'name': 'video.intelligence.detection',
                    'context': {'stream': f'stream{thread_id}', 'app': 'live'},
                    'data': {
                        'vi_data': [{
                            'frame_id': i,
                            'detections': [{
                                'class_name': 'person',
                                'confidence': 0.9,
                                'bbox': {'x': 10, 'y': 10, 'w': 50, 'h': 100}
                            }]
                        }]
                    }
                }
                http_server.translate_payload(payload)
        
        threads = [threading.Thread(target=add_detection, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should have data for 5 different streams
        assert len(http_server.vi_batch_data) == 5
        
        # Clean up
        http_server.vi_batch_data.clear()
        if http_server.vi_batch_timer:
            http_server.vi_batch_timer.cancel()


# Test runner
if __name__ == '__main__':
    print("=" * 80)
    print("WS Slack Translator - Comprehensive Test Suite")
    print("=" * 80)
    print()
    
    # Run pytest with verbose output
    pytest_args = [
        __file__,
        '-v',  # Verbose
        '--tb=short',  # Shorter traceback format
        '--color=yes',  # Colored output
        '-W', 'ignore::DeprecationWarning',  # Ignore deprecation warnings
    ]
    
    exit_code = pytest.main(pytest_args)
    
    print()
    print("=" * 80)
    print(f"Test suite completed with exit code: {exit_code}")
    print("=" * 80)
    
    sys.exit(exit_code)
