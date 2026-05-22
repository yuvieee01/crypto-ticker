pipeline {
    agent any

    environment {
        REGISTRY_USER   = 'yuvieee01'
        IMAGE_NAME      = 'crypto-sentiment-ticker'
        IMAGE_TAG       = "${BUILD_NUMBER}"
        EC2_USER        = 'ubuntu'
        EC2_HOST        = credentials('ec2-host')          // EC2 public IP stored in Jenkins credentials
        SSH_KEY         = credentials('ec2-ssh-key')       // EC2 .pem private key file stored in Jenkins credentials
    }

    stages {
        stage('Lint & Code Quality') {
            steps {
                echo 'Checking Python code quality...'
                sh 'pip install flake8 && python3 -m flake8 app.py --count --select=E9,F63,F7,F82 --show-source --statistics'
            }
        }

        stage('Build Docker Image') {
            steps {
                echo "Building version ${IMAGE_TAG}..."
                script {
                    customImage = docker.build("${REGISTRY_USER}/${IMAGE_NAME}:${IMAGE_TAG}")
                }
            }
        }

        stage('Push to Registry') {
            steps {
                echo 'Publishing image to Docker Hub...'
                script {
                    docker.withRegistry('', 'docker-hub-credentials') {
                        customImage.push()
                        customImage.push('latest')
                    }
                }
            }
        }

        stage('Deploy to EC2') {
            steps {
                echo 'Deploying stack to EC2 via docker-compose...'
                sshagent(credentials: ['ec2-ssh-key']) {
                    sh """
                        # Copy project files to EC2
                        scp -o StrictHostKeyChecking=no -r \
                            docker-compose.yml \
                            prometheus.yml \
                            grafana/ \
                            ${EC2_USER}@${EC2_HOST}:~/crypto-ticker/

                        # SSH into EC2 and deploy
                        ssh -o StrictHostKeyChecking=no ${EC2_USER}@${EC2_HOST} << 'ENDSSH'
                            cd ~/crypto-ticker

                            # Update the app image to the freshly pushed version
                            export APP_IMAGE=${REGISTRY_USER}/${IMAGE_NAME}:${IMAGE_TAG}

                            # Pull the latest image and restart the stack
                            docker compose pull 2>/dev/null || true
                            docker compose down --remove-orphans
                            docker compose up -d

                            echo "Deployment complete. Stack is running."
ENDSSH
                    """
                }
            }
        }
    }

    post {
        success {
            echo "Pipeline completed successfully! Version ${IMAGE_TAG} is live."
        }
        failure {
            echo "Pipeline failed. Check the logs above to see which stage broke."
        }
    }
}