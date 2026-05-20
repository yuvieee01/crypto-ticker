pipeline {
    agent any

    environment {
        // CHANGE THIS TO YOUR ACTUAL DOCKER HUB USERNAME
        REGISTRY_USER   = 'yuvieee01'

        IMAGE_NAME      = 'crypto-sentiment-ticker'
        IMAGE_TAG       = "${BUILD_NUMBER}" // Automatically uses the Jenkins build number as the tag
        KUBECONFIG_CRED = 'kubeconfig-credentials' // This matches the ID you saved in Step 4.1
    }

    stages {
        stage('Lint & Code Quality') {
            steps {
                echo 'Checking Python code quality...'
                sh 'pip install flake8 --break-system-packages && python3 -m flake8 app.py --count --select=E9,F63,F7,F82 --show-source --statistics'
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
                    // Uses the Docker Hub credentials you saved in Step 4.1
                    docker.withRegistry('', 'docker-hub-credentials') {
                        customImage.push()
                        customImage.push('latest')
                    }
                }
            }
        }

        stage('Deploy to Kubernetes') {
            steps {
                echo 'Setting up kubectl and updating the application in the cluster...'
                withCredentials([file(credentialsId: 'kubeconfig-file', variable: 'KUBECONFIG')]) {
                    sh '''
                        # 1. Download the latest stable kubectl binary
                        curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"

                        # 2. Make the binary executable
                        chmod +x ./kubectl
                        
                        # 3. Use the local ./kubectl binary to apply your manifests
                        ./kubectl apply -f k8s/deployment.yaml --kubeconfig=${KUBECONFIG}
                        ./kubectl apply -f k8s/service.yaml --kubeconfig=${KUBECONFIG}
                    '''
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