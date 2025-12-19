from flask import Flask, render_template, request, jsonify, session
import subprocess
import tempfile
import os
import json
import uuid

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# Load problems from JSON file
def load_problems():
    with open('data/problems.json', 'r') as f:
        return json.load(f)

@app.route('/')
def index():
    problems = load_problems()
    return render_template('index.html', problems=problems)

@app.route('/challenge/<problem_id>')
def challenge(problem_id):
    problems = load_problems()
    problem = next((p for p in problems if p['id'] == problem_id), None)
    if not problem:
        return "Problem not found", 404
    submissions = session.get('submissions', {}).get(problem_id, [])
    return render_template('challenge.html', problem=problem, submissions=submissions)

@app.route('/history/<problem_id>')
def history(problem_id):
    submissions = session.get('submissions', {}).get(problem_id, [])
    return jsonify(submissions)

@app.route('/submit/<problem_id>', methods=['POST'])
def submit(problem_id):
    problems = load_problems()
    problem = next((p for p in problems if p['id'] == problem_id), None)
    if not problem:
        return jsonify({'success': False, 'error': 'Problem not found'}), 404
    
    code = request.json.get('code', '')
    
    # Run the code with test cases
    results = run_tests(code, problem['tests'], problem.get('setup_code', ''))
    
    # Track submission in session
    if 'submissions' not in session:
        session['submissions'] = {}
    if problem_id not in session['submissions']:
        session['submissions'][problem_id] = []
    session['submissions'][problem_id].append({
        'id': str(uuid.uuid4())[:8],
        'passed': results['all_passed'],
        'results': results['test_results']
    })
    session.modified = True
    
    return jsonify(results)

def run_tests(code, tests, setup_code=''):
    results = {
        'all_passed': True,
        'test_results': []
    }
    
    for i, test in enumerate(tests):
        test_result = run_single_test(code, test, setup_code)
        results['test_results'].append(test_result)
        if not test_result['passed']:
            results['all_passed'] = False
    
    return results

def run_single_test(code, test, setup_code=''):
    # Create a temporary file with the code and test
    full_code = f"""
{setup_code}

{code}

# Test execution
try:
    result = {test['input']}
    expected = {test['expected']}
    assert result == expected, f"Expected {{expected}}, got {{result}}"
    print("PASS")
except AssertionError as e:
    print(f"FAIL: {{e}}")
except Exception as e:
    print(f"ERROR: {{e}}")
"""
    
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(full_code)
            temp_path = f.name
        
        # Run with timeout for safety
        result = subprocess.run(
            ['python3', temp_path],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        output = result.stdout.strip()
        error = result.stderr.strip()
        
        if output.startswith('PASS'):
            return {'passed': True, 'message': 'Test passed', 'hidden': test.get('hidden', False)}
        elif output.startswith('FAIL'):
            return {'passed': False, 'message': output, 'hidden': test.get('hidden', False)}
        else:
            return {'passed': False, 'message': error or output or 'Unknown error', 'hidden': test.get('hidden', False)}
            
    except subprocess.TimeoutExpired:
        return {'passed': False, 'message': 'Timeout: Code took too long to execute', 'hidden': test.get('hidden', False)}
    except Exception as e:
        return {'passed': False, 'message': str(e), 'hidden': test.get('hidden', False)}
    finally:
        if 'temp_path' in locals():
            os.unlink(temp_path)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
